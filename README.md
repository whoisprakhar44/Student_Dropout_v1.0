# Curated School Datamodel Agent

Local FastAPI + LangGraph demo for querying the `curated_datamodels` school data model with MCP tools.

## Components

| Component | Technology |
|-----------|------------|
| Web UI + REST API | FastAPI + `static/index.html` |
| Sample data | SQLite `database/schema.db` generated from curated YAML |
| Chat / NL queries | LangGraph agent via `POST /ask` |
| Schema retrieval | MCP `retrive_schema_rag` + Milvus Lite |
| SQL execution | MCP `execute_sql` against SQLite |
| Hive path | Disabled MCP stub in `MCP/mcp_hive_execution.py` |

## Layout

```text
app.py
create_schema.py
database/schema.db
schema/curated_datamodels/
  database.yaml
  full_schema.yaml
  tables/
  joins/join_relations.yaml
MCP/
  mcp_rag.py
  mcp_rag.yaml
  mcp_sql_execution.py
  mcp_hive_execution.py
  build_milvus_index.py
my_agent/
```

## Setup & Linux Deployment Steps

Follow these steps to deploy and run this project on a Linux server:

### 1. Extract the Project
Upload the project zip file to your Linux server and unzip it:
```bash
unzip "Student Dropout_v1.0.zip" -d student_dropout
cd student_dropout
```

### 2. Install UV (Fast Python Package Manager)
We recommend using `uv` to manage the virtual environment and install dependencies:
```bash
# Install uv locally
curl -LsSf https://astral.sh/uv/install.sh | sh

# Source shell or restart terminal to make uv available
source $HOME/.local/bin/env
```

### 3. Create and Activate Virtual Environment
```bash
# Create venv using uv
uv venv

# Activate venv
source .venv/bin/activate
```

### 4. Install Dependencies
```bash
uv pip install -r requirements.txt
```

### 5. Install and Run Ollama
If Ollama is not yet installed on the Linux server:
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull the models required by the application
ollama pull qwen3.5:2b
ollama pull nomic-embed-text
```
Ensure the Ollama service is running (usually started automatically via systemd; otherwise run `ollama serve` in a background screen or tmux session).

### 6. Configure Environment Variables
Review the configurations in `.env`. Ensure that the host and model details are correct. 
* To run in SQLite mode: Set `HIVE_MCP_ENABLED=false`.
* To run in Hive mode: Set `HIVE_MCP_ENABLED=true` and provide Hive connection details.

### 7. Seed Database and Vector Index
Before launching, you must initialize the local DB tables and rebuild the vector database for RAG context:
```bash
# 1. Generate the SQLite database and seed 1000 sample students
python create_schema.py

# 2. Rebuild the local Milvus Lite vector index from schema YAMLs
python MCP/build_milvus_index.py
```

### 8. Run the Application
Start the FastAPI server. Specify `--host 0.0.0.0` so that it accepts external connections:
```bash
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```
Open your browser and navigate to `http://<your-server-ip>:8000` to interact with the dashboard.

## Agent Flow

The graph starts at the LLM. The LLM decides whether to call:

- `retrive_schema_rag` for curated table DDL and join relations.
- `execute_sql` for read-only SQLite `SELECT` queries.

There is no deterministic retrieval node before every request.

## Database

`create_schema.py` parses `schema/curated_datamodels/tables/*.yaml`, creates all 25 curated tables in SQLite, and seeds coherent sample school, student, attendance, performance, meal, scheme, and infrastructure data.

Regenerate local data:

```bash
python create_schema.py
```

## Hive Stub

`MCP/mcp_hive_execution.py` exposes `execute_hive_sql`, but it is disabled and not wired into the default graph. Set `HIVE_MCP_ENABLED=true` plus Hive connection env vars only when implementing the active Hive backend.
