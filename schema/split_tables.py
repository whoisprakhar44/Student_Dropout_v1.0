"""
Split full_schema.yaml into one YAML per table under tables/.

Usage (from project root):
    python -m schema.split_tables
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from schema.paths import DATABASE_META_YAML, FULL_SCHEMA_YAML, TABLES_DIR


def split_from_full(
    src_path: Path | None = None,
    out_dir: Path | None = None,
) -> list[Path]:
    src = src_path or FULL_SCHEMA_YAML
    dest = out_dir or TABLES_DIR

    text = src.read_text(encoding="utf-8")
    header_end = text.find("\n- table:")
    if header_end == -1:
        raise ValueError(f"No table entries found in {src}")

    header = text[:header_end].strip()
    tables_block = text[header_end + 1 :]
    for marker in (
        "\n# -----------------------------------------------------------------------------\n# Relationship Summary",
        "\nrelationships:",
    ):
        idx = tables_block.find(marker)
        if idx != -1:
            tables_block = tables_block[:idx]

    header_doc = yaml.safe_load(header) or {}
    database_name = header_doc.get("database", "curated_datamodels")

    if DATABASE_META_YAML.is_file():
        meta = yaml.safe_load(DATABASE_META_YAML.read_text(encoding="utf-8")) or {}
        database_name = meta.get("database", database_name)

    dest.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for chunk in re.split(r"\n(?=- table:)", tables_block.strip()):
        chunk = chunk.strip()
        if not chunk:
            continue
        if not chunk.startswith("- table:"):
            chunk = "- table:\n" + chunk if chunk.startswith("table:") else "- " + chunk

        entry = yaml.safe_load(chunk)
        if not entry or not isinstance(entry, list):
            continue

        table_doc = entry[0]
        table_name = table_doc.get("table")
        if not table_name:
            continue

        out_path = dest / f"{table_name}.yaml"
        doc = {
            "database": database_name,
            "table": table_name,
            **{k: v for k, v in table_doc.items() if k != "table"},
        }
        with out_path.open("w", encoding="utf-8") as f:
            yaml.dump(doc, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        written.append(out_path)

    return written


if __name__ == "__main__":
    paths = split_from_full()
    print(f"Wrote {len(paths)} table YAML files to {TABLES_DIR}")
