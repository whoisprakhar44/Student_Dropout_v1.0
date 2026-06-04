"""
Build Milvus Lite schema index from schema/curated_datamodels/.

Run from project root (Ollama + nomic-embed-text required):
    python MCP/build_milvus_index.py

Regenerate per-table YAMLs from full_schema.yaml:
    python -m schema.split_tables
"""
import os
import sys

import requests
import yaml

MCP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(MCP_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from schema.paths import JOIN_RELATIONS_YAML, TABLES_DIR, ensure_table_yaml_files  # noqa: E402

CONFIG_PATH = os.path.join(MCP_DIR, "mcp_rag.yaml")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_milvus_uri(cfg: dict) -> str:
    uri = cfg["vector_db"]["milvus"]["uri"]
    if uri.startswith(("http://", "https://")) or os.path.isabs(uri):
        return uri
    return os.path.join(MCP_DIR, uri.lstrip("./"))


def load_table_chunks(yaml_files: list) -> list[dict]:
    chunks = []
    for path in yaml_files:
        path = str(path)
        with open(path, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f)
        if not doc:
            continue

        table_name = doc.get("table") or os.path.splitext(os.path.basename(path))[0]
        database_name = doc.get("database", "curated_datamodels")
        raw_ddl = (doc.get("raw_ddl") or "").strip()
        description = doc.get("description", "")

        col_lines = []
        for col in doc.get("columns") or []:
            name = col.get("name", "")
            ctype = col.get("type", "")
            desc = col.get("description", "")
            col_lines.append(f"- {name} ({ctype}): {desc}")

        relationships = doc.get("relationships") or []
        rel_text = "\n".join(f"- {r}" for r in relationships) if relationships else ""

        embedding_text = (
            f"Table: {table_name}\n"
            f"Database: {database_name}\n"
            f"Description: {description}\n"
            f"Columns:\n" + "\n".join(col_lines) + "\n"
            f"Relationships:\n{rel_text}\n"
            f"DDL:\n{raw_ddl}"
        ).strip()

        chunks.append({
            "database_name": database_name,
            "table_name": table_name,
            "raw_ddl": raw_ddl,
            "embedding_text": embedding_text,
        })
    return chunks


def load_join_chunks() -> list[dict]:
    if not JOIN_RELATIONS_YAML.is_file():
        return []

    with open(JOIN_RELATIONS_YAML, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}

    database_name = doc.get("database", "curated_datamodels")
    joins = doc.get("joins") or []
    lines = [doc.get("description", "Join relations for curated school data model.")]
    for join in joins:
        lines.append(
            "{name}: {from_table}.{from_column} -> {to_table}.{to_column} "
            "({cardinality}). Usage: {usage}".format(
                name=join.get("name", "join"),
                from_table=join.get("from_table", ""),
                from_column=join.get("from_column", ""),
                to_table=join.get("to_table", ""),
                to_column=join.get("to_column", ""),
                cardinality=join.get("cardinality", "unknown"),
                usage=join.get("usage", ""),
            )
        )

    embedding_text = "Database: {db}\nChunk: join_relations\n{body}".format(
        db=database_name,
        body="\n".join(lines),
    )
    return [{
        "database_name": database_name,
        "table_name": "__join_relations__",
        "raw_ddl": "",
        "embedding_text": embedding_text,
    }]


_MAX_EMBED_CHARS = 4096  # ~1024 tokens; keeps Ollama context safe


def embed_text(text: str, cfg: dict) -> list[float]:
    emb_cfg = cfg["embedding"]
    if emb_cfg["provider"] != "ollama":
        raise ValueError("Only ollama embeddings supported for index build")

    url = emb_cfg.get("ollama_url", "http://localhost:11434/api/embeddings")
    model = emb_cfg["model"]
    # Truncate to avoid Ollama 500s on huge DDLs
    prompt = text[:_MAX_EMBED_CHARS]
    res = requests.post(url, json={"model": model, "prompt": prompt}, timeout=120)
    res.raise_for_status()
    return res.json()["embedding"]


def build_index():
    cfg = load_config()
    collection = cfg["vector_db"]["milvus"]["collection"]
    dim = cfg["vector_db"]["milvus"]["dim"]
    uri = resolve_milvus_uri(cfg)

    yaml_files = ensure_table_yaml_files()
    chunks = load_table_chunks(yaml_files) + load_join_chunks()
    if not chunks:
        print(f"No schema chunks to index under {TABLES_DIR}.", file=sys.stderr)
        sys.exit(1)

    rows = []
    skipped = 0
    for i, chunk in enumerate(chunks):
        try:
            vector = embed_text(chunk["embedding_text"], cfg)
        except Exception as exc:
            print(
                f"  [SKIP] {chunk['table_name']}: embedding failed — {exc}",
                file=sys.stderr,
            )
            skipped += 1
            continue
        rows.append({
            "id": i,
            "vector": vector,
            "database_name": chunk["database_name"],
            "table_name": chunk["table_name"],
            "raw_ddl": chunk["raw_ddl"][:65000],
            "embedding_text": chunk["embedding_text"][:65000],
        })
    if skipped:
        print(f"  Warning: {skipped} chunk(s) skipped due to embedding errors.", file=sys.stderr)

    from pymilvus import MilvusClient

    client = MilvusClient(uri=uri)
    if client.has_collection(collection):
        client.drop_collection(collection)

    client.create_collection(
        collection_name=collection,
        dimension=dim,
        metric_type=cfg["vector_db"]["milvus"].get("metric_type", "COSINE"),
        auto_id=True,
        enable_dynamic_field=True,
    )

    client.insert(collection_name=collection, data=rows)
    client.load_collection(collection)

    print(f"Indexed {len(rows)} schema chunks from {TABLES_DIR} and {JOIN_RELATIONS_YAML}")
    print(f"  → {uri} (collection={collection})")


if __name__ == "__main__":
    build_index()
