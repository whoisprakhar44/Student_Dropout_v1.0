"""
Canonical paths for curated schema YAML (RAG indexing + maintenance).
"""
from __future__ import annotations

from pathlib import Path

SCHEMA_ROOT = Path(__file__).resolve().parent
DATABASE_SLUG = "curated_datamodels"
DATABASE_DIR = SCHEMA_ROOT / DATABASE_SLUG
TABLES_DIR = DATABASE_DIR / "tables"
JOINS_DIR = DATABASE_DIR / "joins"
JOIN_RELATIONS_YAML = JOINS_DIR / "join_relations.yaml"
FULL_SCHEMA_YAML = DATABASE_DIR / "full_schema.yaml"
DATABASE_META_YAML = DATABASE_DIR / "database.yaml"


def list_table_yaml_files() -> list[Path]:
    if not TABLES_DIR.is_dir():
        return []
    return sorted(TABLES_DIR.glob("*.yaml"))


def ensure_table_yaml_files() -> list[Path]:
    """Return per-table YAMLs, splitting full_schema.yaml if tables/ is empty."""
    existing = list_table_yaml_files()
    if existing:
        return existing
    if not FULL_SCHEMA_YAML.is_file():
        raise FileNotFoundError(
            f"No table YAMLs in {TABLES_DIR} and missing {FULL_SCHEMA_YAML}"
        )
    from schema.split_tables import split_from_full

    return split_from_full()
