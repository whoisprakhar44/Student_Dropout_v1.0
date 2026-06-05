"""
hive_executor.py
────────────────
Reusable HiveExecutor class for production Hive/Iceberg query execution.

Features
────────
  • Config-driven — all infra values come from hive_config.yaml
  • Kerberos authentication via PyHive
  • Lazy-connect + auto-reconnect on failure
  • Session settings applied once per connection (and after every reconnect)
  • SQL validation (SELECT-only; blocks DML/DDL even inside CTEs)
  • Transparent KeyError 22 (timestamptz) fix — three layers:
      Layer 1: PyHive type-map patch at import (fixes SELECT * and all queries)
      Layer 2: SELECT-projection CAST rewrite for explicit column lists
               (only touches the SELECT list — WHERE/GROUP BY/ORDER BY untouched)
      Layer 3: post-fetch safety cast on result rows
  • Timeout with cursor.cancel() — cancels the server-side query, not just the thread
  • Structured JSON results matching the existing MCP contract
  • health_check() method for startup validation (Kerberos + TCP + database)

CDP / Cloudera Iceberg Vectorized Reader Incompatibility
────────────────────────────────────────────────────────
The CDP cluster contains a runtime incompatibility in the Hive vectorized
execution path for Iceberg tables.  Every SELECT against an Iceberg table
fails with:

    java.lang.NoSuchMethodError:
        org.apache.iceberg.parquet.ParquetSchemaUtil.hasIds(
            org.apache.parquet.schema.MessageType)

Root cause: version skew between the cluster's Iceberg JAR and Parquet JAR
in the vectorized reader code path.  This is a cluster-side issue that
cannot be fixed from the client.

Workaround: disable Hive vectorized execution for every session by sending

    SET hive.vectorized.execution.enabled=false

immediately after connection establishment.  HiveExecutor does this
automatically for every new connection (and every auto-reconnect) via
_apply_session_settings().  The statements to execute are configured in
hive_config.yaml under execution.session_settings.

PyHive type-id 22 / timestamp with local time zone
────────────────────────────────────────────────────
Hive type code 22 (TIMESTAMPTZ / timestamp with local time zone) is absent
from PyHive's TTypeId._VALUES_TO_NAMES dict.  PyHive raises KeyError: 22
when parsing cursor.description — *before* any rows are returned.
This is handled by three defensive layers (see Features above).

JSON result contract (matches mcp_sql_execution.py)
────────────────────────────────────────────────────
  success → { status, columns, rows, row_count }
  error   → { status, error_type, error_msg, query }
"""

import json
import logging
import os
import re
import shutil
import socket
import subprocess
import threading
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("hive_executor")


# ─────────────────────────────────────────────────────────────────────────────
#  KeyError 22 — Root-cause fix (Layer 1)
#
#  PyHive resolves column types by looking up type_id in:
#      pyhive.TCLIService.ttypes.TTypeId._VALUES_TO_NAMES
#  Hive type code 22 = TIMESTAMPTZ is not in the original dict, so PyHive
#  raises KeyError: 22 while parsing cursor.description — *before* any rows
#  are returned.  This means a post-fetch cast cannot save SELECT * queries.
#
#  Fix: patch the dict at import time so type 22 is recognised as a STRING-
#  compatible type.  This works for ALL query shapes including SELECT *.
# ─────────────────────────────────────────────────────────────────────────────
def _patch_pyhive_type_map() -> None:
    try:
        from pyhive.TCLIService import ttypes  # type: ignore[import]
        if 22 not in ttypes.TTypeId._VALUES_TO_NAMES:
            ttypes.TTypeId._VALUES_TO_NAMES[22] = "TIMESTAMPTZ_TYPE"
            ttypes.TTypeId._NAMES_TO_VALUES["TIMESTAMPTZ_TYPE"] = 22
            logger.info("PyHive type map patched: added TIMESTAMPTZ_TYPE (22)")
    except Exception as exc:  # pragma: no cover
        logger.warning("Could not patch PyHive type map: %s", exc)


_patch_pyhive_type_map()


# ─────────────────────────────────────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────────────────────────────────────

def _load_config(config_path: str | None = None) -> dict:
    candidates = []
    if config_path:
        candidates.append(Path(config_path))
    candidates.append(Path(__file__).parent / "hive_config.yaml")
    candidates.append(Path.cwd() / "hive_config.yaml")

    for p in candidates:
        if p.exists():
            with open(p) as f:
                cfg = yaml.safe_load(f)
            logger.info("Loaded hive config from: %s", p)
            return cfg

    raise FileNotFoundError(
        "hive_config.yaml not found. Searched: "
        + ", ".join(str(p) for p in candidates)
    )


# ─────────────────────────────────────────────────────────────────────────────
#  SQL Validation
#  Strategy: block forbidden keywords anywhere in the query, regardless of
#  whether they appear inside a CTE body, after a WITH clause, etc.
#  The validator does NOT rely on the first keyword alone.
# ─────────────────────────────────────────────────────────────────────────────

_FORBIDDEN_KEYWORDS = [
    # DML
    "insert", "update", "delete", "merge",
    # DDL
    "create", "drop", "truncate", "alter",
    # Hive-specific DDL / admin
    "msck", "repair", "load",
    # Privilege / session
    "replace", "grant", "revoke",
    # Transaction / proc
    "commit", "rollback", "exec", "call", "lock", "unlock",
]

_FORBIDDEN_PATTERN = re.compile(
    r"\b(" + "|".join(_FORBIDDEN_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


def _validate_query(query: str) -> tuple[bool, str]:
    """
    Allow only read-only SELECT / WITH…SELECT queries.

    Checks:
      1. Non-empty after stripping comments.
      2. Starts with SELECT or WITH.
      3. No forbidden keyword anywhere in the query body
         (catches  WITH x AS (...) INSERT INTO ...).
      4. No multiple statements (more than one semicolon).

    Returns (is_valid, reason).
    """
    if not query or not query.strip():
        return False, "Empty query"

    # Strip SQL comments before checking
    cleaned = re.sub(r"--.*?$", "", query, flags=re.MULTILINE)
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL).strip()

    if not cleaned:
        return False, "Query is empty after stripping comments"

    # Only one statement (single trailing semicolon allowed)
    if ";" in cleaned[:-1]:
        return False, "Multiple SQL statements are not allowed"

    lowered = cleaned.lower()

    if not lowered.startswith(("select", "with")):
        return False, "Only SELECT queries are allowed"

    # Scan the full query body — blocks DML even inside CTE bodies
    match = _FORBIDDEN_PATTERN.search(lowered)
    if match:
        return False, f"Forbidden SQL keyword detected: '{match.group()}'"

    return True, "OK"


# ─────────────────────────────────────────────────────────────────────────────
#  SQL Rewrite Layer — KeyError 22 (Layer 2)
#
#  Scope: SELECT projection only.
#  Purpose: Belt-and-suspenders on top of the PyHive type-map patch.
#           If a column is explicitly listed in SELECT, we CAST it to STRING
#           before sending the query.  WHERE / GROUP BY / ORDER BY / JOIN
#           conditions are never touched.
#
#  Rules:
#    • Bare column name:   created_date  → CAST(created_date AS STRING) AS created_date
#    • Alias.column:       t.created_date → CAST(t.created_date AS STRING) AS created_date
#    • Inside a function:  max(created_date) → left unchanged (anchored match fails)
#    • SELECT *            → left unchanged (Layer 1 handles this)
# ─────────────────────────────────────────────────────────────────────────────

def _rewrite_select_columns(query: str, timestamptz_cols: list[str]) -> str:
    """
    Rewrite timestamptz column references in the SELECT projection only.

    Only bare column names (with optional alias prefix) are rewritten.
    Expressions like max(created_date) are left untouched because the
    anchored regex cannot match them.
    """
    if not timestamptz_cols:
        return query

    upper = query.upper()
    select_pos = upper.find("SELECT")
    if select_pos == -1:
        return query

    # Find the first top-level FROM after SELECT
    depth = 0
    from_pos = -1
    i = select_pos + len("SELECT")
    while i < len(query):
        ch = query[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and query[i : i + 4].upper() == "FROM":
            from_pos = i
            break
        i += 1

    if from_pos == -1:
        return query

    projection = query[select_pos + len("SELECT") : from_pos]

    # SELECT * → skip (Layer 1 type-map patch handles it)
    if projection.strip() == "*":
        return query

    # Build per-column rewrite patterns (anchored, case-insensitive)
    _col_patterns = {
        col: re.compile(r"^(?:\w+\.)?" + re.escape(col) + r"$", re.IGNORECASE)
        for col in timestamptz_cols
    }

    def _replace_col(col_expr: str) -> str:
        stripped = col_expr.strip()
        for tz_col, pattern in _col_patterns.items():
            if pattern.match(stripped):
                return f" CAST({stripped} AS STRING) AS {tz_col}"
        return col_expr

    # Split on top-level commas (respecting nested parentheses)
    parts: list[str] = []
    current = ""
    depth = 0
    for ch in projection:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    if current:
        parts.append(current)

    rewritten_parts = [_replace_col(p) for p in parts]
    new_projection = ",".join(rewritten_parts)

    return (
        query[: select_pos + len("SELECT")]
        + new_projection
        + " "           # ensure whitespace before FROM
        + query[from_pos:]
    )


def _cast_timestamptz_rows(
    rows: list[dict],
    timestamptz_cols: list[str],
) -> list[dict]:
    """
    Post-fetch safety net: cast any remaining timestamptz values in result
    rows to str.  Handles edge cases where Layer 1 and Layer 2 may not have
    fully covered a particular query shape.
    """
    if not timestamptz_cols or not rows:
        return rows

    tz_set = {c.lower() for c in timestamptz_cols}
    return [
        {
            k: (str(v) if k.lower() in tz_set and v is not None else v)
            for k, v in row.items()
        }
        for row in rows
    ]


# ─────────────────────────────────────────────────────────────────────────────
#  HiveExecutor
# ─────────────────────────────────────────────────────────────────────────────

class HiveExecutor:
    """
    Production Hive query executor with Kerberos authentication.

    Usage
    ─────
        executor = HiveExecutor()                       # loads hive_config.yaml
        executor = HiveExecutor("path/to/config.yaml")

        result_json = executor.execute(
            "SELECT COUNT(*) FROM curated_datamodels.citizen_student"
        )
    """

    def __init__(self, config_path: str | None = None):
        self._cfg       = _load_config(config_path)
        self._hive_cfg  = self._cfg["hive"]
        self._exec_cfg  = self._cfg.get("execution", {})
        self._timeout   = int(self._exec_cfg.get("query_timeout_seconds", 300))
        self._tz_cols: list[str] = self._exec_cfg.get("timestamptz_columns", [])
        self._conn      = None
        self._lock      = threading.Lock()

        # Session settings are applied once per connection (and on reconnect).
        # Default ensures vectorized execution is disabled to work around the
        # CDP Iceberg/Parquet NoSuchMethodError (see module docstring).
        _default_session_settings = ["SET hive.vectorized.execution.enabled=false"]
        self._session_settings: list[str] = (
            self._exec_cfg.get("session_settings") or _default_session_settings
        )

        logger.info(
            "HiveExecutor init — host=%s port=%s auth=%s timeout=%ss "
            "tz_cols=%s session_settings=%s",
            self._hive_cfg["host"],
            self._hive_cfg["port"],
            self._hive_cfg["auth"],
            self._timeout,
            self._tz_cols,
            self._session_settings,
        )

    # ── Connection management ─────────────────────────────────────────────────

    def _connect(self):
        from pyhive import hive  # type: ignore[import]

        logger.info(
            "[connect] Connecting to HiveServer2 %s:%s (auth=%s service=%s)",
            self._hive_cfg["host"],
            self._hive_cfg["port"],
            self._hive_cfg["auth"],
            self._hive_cfg.get("kerberos_service_name", "hive"),
        )
        self._conn = hive.Connection(
            host=self._hive_cfg["host"],
            port=int(self._hive_cfg["port"]),
            auth=self._hive_cfg["auth"],
            kerberos_service_name=self._hive_cfg.get("kerberos_service_name", "hive"),
        )
        logger.info("[connect] HiveServer2 connection established")

        # Apply session-scoped settings immediately after every new connection.
        # This is the sole place they are sent — NOT before every query.
        self._apply_session_settings()

    def _apply_session_settings(self) -> None:
        """
        Execute all configured session_settings statements on the current
        connection.  Called once after _connect() — including after every
        auto-reconnect — so settings are always active for the lifetime of
        the connection.

        Critically, this is where vectorized execution is disabled to work
        around the CDP Iceberg/Parquet NoSuchMethodError (see module docstring).

        Errors are logged as WARNING rather than raised so that a mis-typed
        SET statement does not crash the server — queries will still execute,
        just without that particular setting applied.
        """
        if not self._session_settings or self._conn is None:
            return

        cursor = self._conn.cursor()
        try:
            for stmt in self._session_settings:
                try:
                    logger.info("[session] Applying: %s", stmt)
                    cursor.execute(stmt)
                    logger.info("[session] Applied:  %s", stmt)
                except Exception as exc:
                    logger.warning(
                        "[session] Failed to apply %r: %s — "
                        "queries will still execute but setting may be inactive",
                        stmt,
                        exc,
                    )
        finally:
            try:
                cursor.close()
            except Exception:
                pass

    def _get_connection(self):
        if self._conn is None:
            self._connect()
        return self._conn

    def _reset_connection(self):
        """Close the current connection and mark it as gone so the next call
        to _get_connection() triggers a fresh _connect() — which will also
        re-apply all session settings automatically."""
        logger.info("[reconnect] Resetting Hive connection")
        try:
            if self._conn is not None:
                self._conn.close()
        except Exception:
            pass
        self._conn = None
        logger.info("[reconnect] Connection reset complete — will reconnect on next query")

    # ── Health check ──────────────────────────────────────────────────────────

    def health_check(self) -> dict:
        """
        Run three diagnostic checks and return a structured result dict.

        Returns
        ───────
        {
            "kerberos":   {"ok": bool, "detail": str},
            "hiveserver": {"ok": bool, "detail": str},
            "database":   {"ok": bool, "detail": str},
            "all_ok":     bool,
        }

        Sub-checks
        ──────────
        kerberos   — runs `klist`, parses the default principal line
        hiveserver — TCP socket-connect to host:port (no PyHive dependency)
        database   — opens a fresh cursor, runs SHOW DATABASES, also validates
                     that session settings can be applied on the connection
        """
        result: dict[str, Any] = {}

        # ── 1. Kerberos ticket ────────────────────────────────────────────────
        logger.info("[health] Checking Kerberos ticket")
        kerberos_ok, kerberos_detail = self._check_kerberos()
        result["kerberos"] = {"ok": kerberos_ok, "detail": kerberos_detail}
        if kerberos_ok:
            logger.info("[health] Kerberos OK — %s", kerberos_detail)
        else:
            logger.warning("[health] Kerberos FAILED — %s", kerberos_detail)

        # ── 2. HiveServer2 TCP ────────────────────────────────────────────────
        logger.info("[health] Checking HiveServer2 TCP connectivity")
        hs2_ok, hs2_detail = self._check_hiveserver_tcp()
        result["hiveserver"] = {"ok": hs2_ok, "detail": hs2_detail}
        if hs2_ok:
            logger.info("[health] HiveServer2 TCP OK — %s", hs2_detail)
        else:
            logger.warning("[health] HiveServer2 TCP FAILED — %s", hs2_detail)

        # ── 3. Database query (SHOW DATABASES) ────────────────────────────────
        logger.info("[health] Checking Hive database access")
        db_ok, db_detail = self._check_database()
        result["database"] = {"ok": db_ok, "detail": db_detail}
        if db_ok:
            logger.info("[health] Database OK — %s", db_detail)
        else:
            logger.error("[health] Database FAILED — %s", db_detail)

        result["all_ok"] = all(
            result[k]["ok"] for k in ("kerberos", "hiveserver", "database")
        )
        logger.info("[health] Health check complete — all_ok=%s", result["all_ok"])
        return result

    def _check_kerberos(self) -> tuple[bool, str]:
        """Validate Kerberos ticket via klist subprocess."""
        klist = shutil.which("klist")
        if not klist:
            return False, "klist not found on PATH — krb5-workstation not installed"
        try:
            proc = subprocess.run(
                [klist],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            return False, "klist timed out after 10s"
        except Exception as exc:
            return False, f"klist failed to run: {exc}"

        if proc.returncode != 0:
            return (
                False,
                f"No valid Kerberos ticket (klist exit {proc.returncode}). "
                f"Run: kinit <principal>. stderr: {proc.stderr.strip()}",
            )

        # Extract principal for display
        principal = ""
        for line in proc.stdout.splitlines():
            if "principal" in line.lower():
                principal = line.strip()
                break
        return True, principal or "ticket present"

    def _check_hiveserver_tcp(self) -> tuple[bool, str]:
        """TCP socket connect to HiveServer2 — no PyHive dependency."""
        host = self._hive_cfg["host"]
        port = int(self._hive_cfg["port"])
        try:
            with socket.create_connection((host, port), timeout=10):
                pass
        except OSError as exc:
            return False, f"Cannot reach {host}:{port} — {exc}"
        return True, f"TCP {host}:{port} reachable"

    def _check_database(self) -> tuple[bool, str]:
        """Open a fresh Hive connection, apply session settings, run SHOW DATABASES."""
        try:
            from pyhive import hive  # type: ignore[import]
        except ImportError:
            return False, "PyHive not installed — run: pip install 'pyhive[hive]' thrift-sasl"

        host = self._hive_cfg["host"]
        port = int(self._hive_cfg["port"])
        auth = self._hive_cfg["auth"]
        ks   = self._hive_cfg.get("kerberos_service_name", "hive")

        try:
            conn = hive.Connection(
                host=host, port=port, auth=auth, kerberos_service_name=ks,
            )
        except Exception as exc:
            return False, f"Connection failed: {exc}"

        try:
            # Apply session settings on this health-check connection too so
            # we validate that path (e.g. the vectorized execution SET).
            cur = conn.cursor()
            for stmt in self._session_settings:
                try:
                    cur.execute(stmt)
                    logger.info("[health/session] Applied: %s", stmt)
                except Exception as exc:
                    logger.warning("[health/session] Failed to apply %r: %s", stmt, exc)

            cur.execute("SHOW DATABASES")
            dbs = [row[0] for row in cur.fetchall()]
            cur.close()
            conn.close()
        except Exception as exc:
            try:
                conn.close()
            except Exception:
                pass
            return False, f"SHOW DATABASES failed: {exc}"

        sample = ", ".join(dbs[:5]) + (" …" if len(dbs) > 5 else "")
        return True, f"SHOW DATABASES OK — [{sample}]"

    # ── Query execution ───────────────────────────────────────────────────────

    def execute(self, query: str) -> str:
        """
        Validate, rewrite, and execute a Hive SQL query.

        Returns JSON matching the MCP contract:
          success → { status, columns, rows, row_count }
          error   → { status, error_type, error_msg, query }
        """
        logger.info("[execute] %s", query[:200])

        # ── 1. Validate ───────────────────────────────────────────────────────
        ok, reason = _validate_query(query)
        if not ok:
            logger.warning("[execute] blocked: %s", reason)
            return json.dumps({
                "status":     "error",
                "error_type": "validation_error",
                "error_msg":  reason,
                "query":      query,
            })

        # ── 2. Layer 2 SQL rewrite (SELECT projection only) ───────────────────
        rewritten_query = _rewrite_select_columns(query, self._tz_cols)
        if rewritten_query != query:
            logger.info("[execute] SQL rewritten (timestamptz CAST injected)")

        # ── 3. Execute with timeout + cursor.cancel() on expiry ───────────────
        result_holder: dict[str, Any] = {}
        error_holder:  dict[str, Any] = {}
        cursor_holder: dict[str, Any] = {}   # shared with timeout handler

        def _run() -> None:
            try:
                with self._lock:
                    conn = self._get_connection()

                cursor = conn.cursor()
                cursor_holder["cursor"] = cursor

                cursor.execute(rewritten_query)

                # cursor.description triggers type-map lookup — Layer 1 patch
                # prevents KeyError 22 here for ALL query shapes including SELECT *
                description = cursor.description or []
                columns = [col[0] for col in description]
                raw_rows = cursor.fetchall()
                cursor.close()

                rows = [dict(zip(columns, row)) for row in raw_rows]

                # Layer 3 post-fetch safety cast
                rows = _cast_timestamptz_rows(rows, self._tz_cols)

                result_holder["columns"]   = columns
                result_holder["rows"]      = rows
                result_holder["row_count"] = len(rows)

            except Exception as exc:
                logger.error("[execute] error: %s", exc, exc_info=True)
                self._reset_connection()
                error_holder["exc"] = exc

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=self._timeout)

        if thread.is_alive():
            # ── Cancel the server-side query to avoid orphaned Hive jobs ─────
            cursor = cursor_holder.get("cursor")
            if cursor is not None:
                try:
                    cursor.cancel()
                    logger.info("[execute] cursor.cancel() sent to HiveServer2")
                except Exception as cancel_exc:
                    logger.warning("[execute] cursor.cancel() failed: %s", cancel_exc)
            self._reset_connection()
            logger.error("[execute] query timed out after %ss", self._timeout)
            return json.dumps({
                "status":     "error",
                "error_type": "timeout_error",
                "error_msg":  (
                    f"Query cancelled after {self._timeout}s timeout. "
                    "The Hive job has been requested to stop."
                ),
                "query": query,
            })

        if error_holder:
            exc = error_holder["exc"]
            exc_str = str(exc)
            # Inform the operator if the patch missed a new timestamptz column
            if isinstance(exc, KeyError) and "22" in exc_str:
                exc_str = (
                    "PyHive KeyError 22 (timestamptz): the type-map patch may "
                    "not have applied.  Ensure pyhive is imported after "
                    "hive_executor.  Also add any new timestamptz column to "
                    "'execution.timestamptz_columns' in hive_config.yaml. "
                    f"Original error: {exc_str}"
                )
            return json.dumps({
                "status":     "error",
                "error_type": "execution_error",
                "error_msg":  exc_str,
                "query":      query,
            })

        return json.dumps(
            {
                "status":    "success",
                "columns":   result_holder["columns"],
                "rows":      result_holder["rows"],
                "row_count": result_holder["row_count"],
            },
            default=str,   # serialises date/datetime/Decimal safely
        )

    def close(self):
        self._reset_connection()
        logger.info("HiveExecutor connection closed")
