from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, AIMessage
from typing import Any, Optional, Literal, List
import sqlite3
import os
import json
from datetime import datetime, date, timedelta
import random
import string

from my_agent.agent import build_graph
from my_agent.utils.ollama_check import chat_model_name, check_ollama
from my_agent.utils.tools import cleanup_tools
import traceback
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from create_schema import create_database

# Database path
DB_PATH = os.path.join(os.path.dirname(__file__), 'database', 'schema.db')

# Session management (simple in-memory for demo)
sessions = {}

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="The user's question.")

class TraceMessage(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: Optional[str | list] = None
    tool_calls: Optional[list[dict[str, Any]]] = None
    tool_name: Optional[str] = None

class AskResponse(BaseModel):
    answer: str
    llm_calls: int
    trace: list[TraceMessage]
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z"
    )

class LoginRequest(BaseModel):
    username: str
    password: str

class User(BaseModel):
    username: str
    email: str = None

class StudentResponse(BaseModel):
    student_adhaar: str
    name: str
    gender: str
    age: int
    school_name: str
    school_id: int
    risk_level: str
    risk_score: float
    current_status: str
    contributing_factors: str
    recommended_intervention: str
    parent_income: int = None

class StatsResponse(BaseModel):
    total_students: int
    critical_risk: int
    high_risk: int
    dropped_out: int
    avg_gpa: float
    avg_attendance: float
    risk_distribution: List[dict]
    status_distribution: List[dict]

def extract_content(m):
    content = getattr(m, "content", None)
    if isinstance(content, list):
        return " ".join(
            block.get("text", "") for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ) or None
    return content or None

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """Initialize curated sample database if missing or still on the old schema."""
    should_create = not os.path.exists(DB_PATH)
    if not should_create:
        try:
            conn = sqlite3.connect(DB_PATH)
            tables = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            conn.close()
            should_create = "citizen_student" not in tables or "students" in tables
        except sqlite3.Error:
            should_create = True

    if should_create:
        create_database(DB_PATH, replace=True)
        print(f"Curated database initialized at {DB_PATH}")

def _http_error_from_exc(exc: Exception) -> HTTPException:
    msg = str(exc)
    model = chat_model_name()
    if "not found" in msg.lower() and "model" in msg.lower():
        return HTTPException(
            status_code=503,
            detail=(
                f"Ollama model '{model}' is not installed. "
                f"Run: ollama pull {model} — then restart uvicorn. ({msg})"
            ),
        )
    return HTTPException(status_code=500, detail=msg)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database()
    ollama_status = check_ollama()
    app.state.ollama_status = ollama_status
    if not ollama_status.get("model_available"):
        print(
            "WARNING: Ollama chat model not available:",
            ollama_status,
        )
    else:
        print("Ollama ready:", ollama_status.get("model"))
    graph = await build_graph()
    app.state.graph = graph
    yield
    await cleanup_tools()

app = FastAPI(title="Student Dropout Prediction API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return FileResponse("static/index.html")

@app.get("/health")
async def health():
    info = check_ollama()
    return {
        "status": "ok" if info.get("model_available") else "degraded",
        **info,
    }

# ========== Authentication APIs ==========
@app.post("/api/login")
async def login(request: LoginRequest):
    """Simple login endpoint"""
    # For demo: accept any username/password
    session_id = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
    sessions[session_id] = {"username": request.username}
    return {"session_id": session_id, "username": request.username}

@app.post("/api/register")
async def register(request: LoginRequest):
    """Simple registration endpoint"""
    return {"message": "Registered successfully"}

@app.get("/api/me")
async def get_me():
    """Get current user"""
    return {"username": "student_user", "email": "user@example.com"}

@app.post("/api/logout")
async def logout():
    """Logout endpoint"""
    return {"message": "Logged out"}

# ========== Dashboard & Stats APIs ==========
@app.get("/api/stats")
async def get_stats():
    """Get dashboard statistics"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Total students
        cursor.execute("SELECT COUNT(DISTINCT citizen_student_pk) as count FROM citizen_student")
        total = cursor.fetchone()['count']
        
        # Risk-like dropped-out proxy from low attendance and low academic performance.
        cursor.execute("""
            WITH attendance AS (
                SELECT citizen_student_id_fk,
                       AVG(CASE WHEN present_flag = 'Y' THEN 1.0 ELSE 0.0 END) AS attendance_rate
                FROM school_student_attendance_fact
                WHERE academic_year = '2023-24'
                GROUP BY citizen_student_id_fk
            ),
            performance AS (
                SELECT citizen_student_id_fk,
                       AVG(percentage_score) AS avg_score
                FROM school_academic_performance_fact
                WHERE academic_year = '2023-24'
                GROUP BY citizen_student_id_fk
            )
            SELECT COUNT(DISTINCT s.citizen_student_pk) as count
            FROM citizen_student s
            LEFT JOIN attendance a ON s.citizen_student_pk = a.citizen_student_id_fk
            LEFT JOIN performance p ON s.citizen_student_pk = p.citizen_student_id_fk
            WHERE COALESCE(a.attendance_rate, 1.0) < 0.60
               OR COALESCE(p.avg_score, 100) < 45
        """)
        dropped = cursor.fetchone()['count']
        
        # Average attendance
        cursor.execute("""
            SELECT AVG(CASE WHEN present_flag = 'Y' THEN 100.0 ELSE 0.0 END) as avg_att
            FROM school_student_attendance_fact
            WHERE academic_year = '2023-24'
        """)
        avg_attendance = cursor.fetchone()['avg_att'] or 0
        
        # Average marks (as GPA substitute)
        cursor.execute("""
            SELECT AVG(percentage_score / 10.0) as avg_gpa
            FROM school_academic_performance_fact
            WHERE academic_year = '2023-24'
        """)
        avg_gpa = cursor.fetchone()['avg_gpa'] or 0
        
        # Risk distribution (simulated)
        critical_risk = int(total * 0.1)
        high_risk = int(total * 0.15)
        
        risk_distribution = [
            {"risk_level": "critical", "count": critical_risk},
            {"risk_level": "high", "count": high_risk},
            {"risk_level": "medium", "count": int(total * 0.25)},
            {"risk_level": "low", "count": int(total * 0.5)},
        ]
        
        # Status distribution
        status_distribution = [
            {"current_status": "active", "count": total - dropped},
            {"current_status": "dropped_out", "count": dropped},
        ]
        
        conn.close()
        
        return {
            "total_students": total,
            "critical_risk": critical_risk,
            "high_risk": high_risk,
            "dropped_out": dropped,
            "avg_gpa": round(avg_gpa, 2),
            "avg_attendance": round(avg_attendance, 1),
            "risk_distribution": risk_distribution,
            "status_distribution": status_distribution,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========== Students APIs ==========
@app.get("/api/students")
async def get_students(skip: int = 0, limit: int = 50):
    """Get list of students with risk assessment"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            WITH attendance AS (
                SELECT citizen_student_id_fk,
                       AVG(CASE WHEN present_flag = 'Y' THEN 100.0 ELSE 0.0 END) AS attendance
                FROM school_student_attendance_fact
                WHERE academic_year = '2023-24'
                GROUP BY citizen_student_id_fk
            ),
            performance AS (
                SELECT citizen_student_id_fk,
                       AVG(percentage_score) AS marks_obtained
                FROM school_academic_performance_fact
                WHERE academic_year = '2023-24'
                GROUP BY citizen_student_id_fk
            )
            SELECT s.student_aadhaar_id AS student_adhaar,
                   s.student_name AS name,
                   s.gender,
                   CAST((strftime('%Y', 'now') - strftime('%Y', s.date_of_birth)) AS INTEGER) AS age,
                   sc.school_name,
                   s.citizen_school_fk AS school_id,
                   a.attendance,
                   p.marks_obtained
            FROM citizen_student s
            LEFT JOIN citizen_school sc ON s.citizen_school_fk = sc.citizen_school_id_pk
            LEFT JOIN attendance a ON s.citizen_student_pk = a.citizen_student_id_fk
            LEFT JOIN performance p ON s.citizen_student_pk = p.citizen_student_id_fk
            ORDER BY s.citizen_student_pk
            LIMIT ? OFFSET ?
        """, (limit, skip))
        
        rows = cursor.fetchall()
        students = []
        
        for row in rows:
            # Calculate risk level
            risk_score = 0.2
            if row['marks_obtained'] and row['marks_obtained'] < 200:
                risk_score += 0.3
            if row['attendance'] and row['attendance'] < 60:
                risk_score += 0.25
            
            risk_level = "critical" if risk_score > 0.6 else "high" if risk_score > 0.4 else "medium" if risk_score > 0.2 else "low"
            
            students.append({
                "student_adhaar": row['student_adhaar'],
                "name": row['name'],
                "gender": row['gender'],
                "age": row['age'],
                "school_name": row['school_name'],
                "school_id": row['school_id'],
                "risk_level": risk_level,
                "risk_score": risk_score,
                "current_status": "dropped_out" if risk_score > 0.6 else "active",
                "contributing_factors": "Low marks, High absence" if risk_score > 0.4 else "None",
                "recommended_intervention": "Academic support, Attendance tracking" if risk_score > 0.4 else "None",
            })
        
        conn.close()
        return students
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/students/{student_id}")
async def get_student_detail(student_id: str):
    """Get detailed student info"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT s.student_aadhaar_id AS student_adhaar,
                   s.student_name AS name,
                   s.gender,
                   s.date_of_birth AS dob,
                   s.social_category,
                   s.address AS place_of_living,
                   b.benefit_amount AS parent_income
            FROM citizen_student s
            LEFT JOIN scheme_benefits_fact b
              ON s.citizen_student_pk = b.citizen_student_id_fk
             AND b.academic_year = '2023-24'
            WHERE s.student_aadhaar_id = ?
        """, (student_id,))
        
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Student not found")
        
        conn.close()
        
        return {
            "student_adhaar": row['student_adhaar'],
            "name": row['name'],
            "gender": row['gender'],
            "dob": row['dob'],
            "parent_income": row['parent_income'],
            "place_of_living": row['place_of_living'],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def _extract_sql_and_data(trace: list[TraceMessage]) -> tuple[str | None, list]:
    sql = None
    data = []
    for msg in trace:
        if msg.role == "assistant" and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc.get("name") == "execute_sql" and tc.get("args", {}).get("query"):
                    sql = tc["args"]["query"]
        if msg.role == "tool" and msg.tool_name == "execute_sql" and msg.content:
            try:
                parsed = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                if parsed.get("status") == "success" and parsed.get("rows"):
                    data = parsed["rows"]
            except (json.JSONDecodeError, TypeError):
                pass
    return sql, data


async def _invoke_agent(question: str) -> AskResponse:
    """Run LangGraph agent: LLM chooses schema retrieval and SQL tools."""
    result = await app.state.graph.ainvoke({
        "user_query": question,
        "messages": [HumanMessage(content=question)],
        "retrieved_context": [],
        "llm_calls": 0,
    })
    messages = result.get("messages", [])
    answer = next(
        (getattr(m, "content", None) for m in reversed(messages)
         if getattr(m, "content", None)),
        None,
    ) or ""

    trace = [
        TraceMessage(
            role=(
                "user" if isinstance(m, HumanMessage) else
                "tool" if m.__class__.__name__ == "ToolMessage" else
                "assistant"
            ),
            content=extract_content(m),
            tool_calls=getattr(m, "tool_calls", None) or None,
            tool_name=getattr(m, "name", None),
        )
        for m in messages
    ]

    return AskResponse(
        answer=answer,
        llm_calls=result.get("llm_calls", 0),
        trace=trace,
    )


def _agent_to_chat_payload(response: AskResponse, thread_id: str | None = None) -> dict:
    """Map agent response for dashboard chat UI (execution + answer, not SQL-only)."""
    sql, data = _extract_sql_and_data(response.trace)
    return {
        "thread_id": thread_id or ("thread_" + "".join(random.choices(string.digits, k=10))),
        "answer": response.answer,
        "summary": response.answer,
        "commentary": response.answer,
        "proposed_sql": sql,
        "sql": sql,
        "data": data,
        "llm_calls": response.llm_calls,
        "trace": [t.model_dump() for t in response.trace],
        "timestamp": response.timestamp,
    }


# ========== Chat APIs — delegate to LangGraph execution agent ==========
@app.post("/api/chat/start")
async def chat_start(payload: AskRequest):
    """Run NL→SQL execution agent (same as /ask)."""
    try:
        response = await _invoke_agent(payload.question)
        return _agent_to_chat_payload(response)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/chat/feedback")
async def chat_feedback(payload: dict):
    """Re-run agent with revised question from feedback."""
    question = payload.get("question") or payload.get("feedback") or ""
    if not question:
        raise HTTPException(status_code=400, detail="question or feedback required")
    try:
        response = await _invoke_agent(question)
        out = _agent_to_chat_payload(response, payload.get("thread_id"))
        return out
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/chat/approve")
async def chat_approve(payload: dict):
    """Legacy approve — re-run agent (SQL already executed inside graph)."""
    question = payload.get("question") or "Summarize the query results."
    try:
        response = await _invoke_agent(question)
        return _agent_to_chat_payload(response, payload.get("thread_id"))
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/chat/history")
async def chat_history():
    """Get chat history"""
    return []


@app.post("/ask", response_model=AskResponse)
async def ask(payload: AskRequest):
    try:
        if not check_ollama().get("model_available"):
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Ollama model '{chat_model_name()}' is not available. "
                    f"Run: ollama pull {chat_model_name()} — then restart uvicorn."
                ),
            )
        return await _invoke_agent(payload.question)
    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise _http_error_from_exc(exc)
