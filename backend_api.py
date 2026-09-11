"""
Cognitive Nexus FastAPI Backend
Provides REST API for Android and other mobile clients.
Wraps existing Streamlit business logic and Ollama integration.
"""

import os
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# Import existing Cognitive Nexus modules
try:
    from modules.providers import check_ollama_status, rank_ollama_models
except ImportError:
    # Fallback if modules not available - must exist for production
    check_ollama_status = None
    rank_ollama_models = None

# ============================================================================
# CONFIGURATION
# ============================================================================

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "llama3.1:8b")
DB_PATH = Path("data/sessions.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title="Cognitive Nexus API",
    description="REST API for Android and mobile clients",
    version="1.0.0",
)

# Enable CORS for mobile clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# DATABASE
# ============================================================================

def init_db():
    """Initialize SQLite database schema."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Conversations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            session_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            title TEXT,
            deleted_at TEXT
        )
    """)
    
    # Messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            model TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES conversations(session_id)
        )
    """)
    
    conn.commit()
    conn.close()

init_db()

def get_db():
    """Get database connection."""
    return sqlite3.connect(DB_PATH)

# ============================================================================
# MODELS / PYDANTIC SCHEMAS
# ============================================================================

class HealthResponse(BaseModel):
    """GET /api/health response."""
    ok: bool
    ollama_available: bool
    chat_model: Optional[str]
    time: str
    detail: Optional[str] = None

class ModelsResponse(BaseModel):
    """GET /api/models response."""
    models: List[str]
    default_model: Optional[str]
    ollama_available: bool

class ConversationSummary(BaseModel):
    """Conversation metadata."""
    session_id: str
    created_at: str
    updated_at: str
    title: Optional[str] = None
    message_count: int

class Message(BaseModel):
    """Chat message."""
    role: str  # "user" or "assistant"
    content: str
    model: Optional[str] = None
    created_at: Optional[str] = None

class ChatRequest(BaseModel):
    """POST /api/chat request."""
    message: str = Field(..., min_length=1)
    session_id: Optional[str] = None
    model: Optional[str] = None

class ChatResponse(BaseModel):
    """POST /api/chat response."""
    reply: str
    session_id: str
    model: str

# ============================================================================
# HEALTH ENDPOINT
# ============================================================================

@app.get("/api/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """
    Check backend and Ollama availability.
    
    Returns:
        HTTP 200 with status details.
        
    Never exposes Ollama URL or internal details.
    """
    if check_ollama_status is None:
        # Fallback if modules not available
        return HealthResponse(
            ok=True,
            ollama_available=False,
            chat_model=CHAT_MODEL,
            time=datetime.utcnow().isoformat(),
            detail="Module initialization required",
        )
    
    try:
        status = check_ollama_status(base_url=OLLAMA_URL, timeout=2.0)
        return HealthResponse(
            ok=status.available,
            ollama_available=status.available,
            chat_model=CHAT_MODEL if status.available else None,
            time=datetime.utcnow().isoformat(),
        )
    except Exception as e:
        return HealthResponse(
            ok=False,
            ollama_available=False,
            chat_model=None,
            time=datetime.utcnow().isoformat(),
            detail="Ollama unavailable or unreachable",
        )

# ============================================================================
# MODELS ENDPOINT
# ============================================================================

@app.get("/api/models", response_model=ModelsResponse)
def get_models() -> ModelsResponse:
    """
    Get list of available Ollama models.
    
    Returns:
        HTTP 200: List of installed models with default.
        HTTP 503: If Ollama is unavailable.
        
    Never exposes Ollama URL to client.
    """
    if check_ollama_status is None:
        raise HTTPException(
            status_code=503,
            detail="Backend module not initialized",
        )
    
    try:
        status = check_ollama_status(base_url=OLLAMA_URL, timeout=2.0)
        
        if not status.available:
            raise HTTPException(
                status_code=503,
                detail="Ollama is unavailable",
            )
        
        models = status.models or []
        
        # Rank models if possible
        if rank_ollama_models and models:
            try:
                ranked = rank_ollama_models(models)
                models = ranked if ranked else models
            except Exception:
                pass  # Use unranked list on error
        
        # Determine default model
        default = None
        if CHAT_MODEL in models:
            default = CHAT_MODEL
        elif models:
            default = models[0]
        
        return ModelsResponse(
            models=models,
            default_model=default,
            ollama_available=True,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail="Ollama is unavailable",
        )

# ============================================================================
# CONVERSATIONS ENDPOINTS
# ============================================================================

@app.get("/api/conversations")
def list_conversations() -> List[ConversationSummary]:
    """
    Get list of all conversations (sessions).
    
    Returns:
        HTTP 200: List of conversation summaries.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT session_id, created_at, updated_at, title
        FROM conversations
        WHERE deleted_at IS NULL
        ORDER BY updated_at DESC
    """)
    
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for session_id, created_at, updated_at, title in rows:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,))
        count = cursor.fetchone()[0]
        conn.close()
        
        result.append(ConversationSummary(
            session_id=session_id,
            created_at=created_at,
            updated_at=updated_at,
            title=title,
            message_count=count,
        ))
    
    return result

@app.post("/api/conversations")
def create_conversation() -> Dict[str, str]:
    """
    Create a new conversation (session).
    
    Returns:
        HTTP 200: New session_id and metadata.
    """
    session_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO conversations (session_id, created_at, updated_at, title)
        VALUES (?, ?, ?, ?)
    """, (session_id, now, now, None))
    conn.commit()
    conn.close()
    
    return {
        "session_id": session_id,
        "created_at": now,
        "updated_at": now,
    }

@app.get("/api/conversations/{session_id}/messages")
def get_conversation_messages(session_id: str) -> List[Message]:
    """
    Get message history for a conversation.
    
    Args:
        session_id: Conversation ID
        
    Returns:
        HTTP 200: List of messages in order.
        HTTP 404: If session not found.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Verify session exists and is not deleted
    cursor.execute("""
        SELECT deleted_at FROM conversations WHERE session_id = ?
    """, (session_id,))
    row = cursor.fetchone()
    
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    if row[0] is not None:
        conn.close()
        raise HTTPException(status_code=404, detail="Conversation is deleted")
    
    # Get messages
    cursor.execute("""
        SELECT role, content, model, created_at
        FROM messages
        WHERE session_id = ?
        ORDER BY created_at ASC
    """, (session_id,))
    
    messages = []
    for role, content, model, created_at in cursor.fetchall():
        messages.append(Message(
            role=role,
            content=content,
            model=model,
            created_at=created_at,
        ))
    
    conn.close()
    return messages

@app.delete("/api/conversations/{session_id}")
def delete_conversation(session_id: str) -> Dict[str, str]:
    """
    Soft-delete a conversation (mark as deleted).
    
    Args:
        session_id: Conversation ID
        
    Returns:
        HTTP 200: Deletion confirmed.
        HTTP 404: If session not found.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT deleted_at FROM conversations WHERE session_id = ?
    """, (session_id,))
    row = cursor.fetchone()
    
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    now = datetime.utcnow().isoformat()
    cursor.execute("""
        UPDATE conversations SET deleted_at = ? WHERE session_id = ?
    """, (now, session_id))
    conn.commit()
    conn.close()
    
    return {"status": "deleted", "session_id": session_id}

# ============================================================================
# CHAT ENDPOINT
# ============================================================================

@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """
    Send a message and get AI response.
    
    Args:
        request: ChatRequest with message, optional session_id and model
        
    Returns:
        HTTP 200: Assistant reply and session info.
        HTTP 400/422: Invalid model or validation error.
        HTTP 503: Ollama unavailable.
        HTTP 504: Ollama timeout.
    """
    # Validate message
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=422, detail="Message cannot be empty")
    
    # Default session_id if not provided
    session_id = request.session_id or str(uuid.uuid4())
    
    # Ensure session exists
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT session_id FROM conversations WHERE session_id = ?", (session_id,))
    if not cursor.fetchone():
        now = datetime.utcnow().isoformat()
        cursor.execute("""
            INSERT INTO conversations (session_id, created_at, updated_at, title)
            VALUES (?, ?, ?, ?)
        """, (session_id, now, now, None))
        conn.commit()
    
    # Determine model to use
    selected_model = request.model or CHAT_MODEL
    
    # Validate selected model is installed
    if check_ollama_status:
        try:
            status = check_ollama_status(base_url=OLLAMA_URL, timeout=2.0)
            if not status.available:
                raise HTTPException(
                    status_code=503,
                    detail="Ollama is unavailable",
                )
            if status.models and selected_model not in status.models:
                raise HTTPException(
                    status_code=400,
                    detail=f"Model '{selected_model}' is not installed on the backend",
                )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=503,
                detail="Ollama is unavailable",
            )
    
    # Store user message
    now = datetime.utcnow().isoformat()
    cursor.execute("""
        INSERT INTO messages (session_id, role, content, model, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (session_id, "user", request.message, selected_model, now))
    conn.commit()
    
    # Call Ollama through existing backend logic (simplified for MVP)
    # In production, integrate with modules/nexus_core.py
    try:
        reply = call_ollama_chat(selected_model, request.message)
    except Exception as e:
        conn.close()
        raise HTTPException(
            status_code=504,
            detail="Failed to get response from Ollama",
        )
    
    # Store assistant response
    cursor.execute("""
        INSERT INTO messages (session_id, role, content, model, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (session_id, "assistant", reply, selected_model, now))
    
    # Update conversation updated_at
    cursor.execute("""
        UPDATE conversations SET updated_at = ? WHERE session_id = ?
    """, (now, session_id))
    conn.commit()
    conn.close()
    
    return ChatResponse(
        reply=reply,
        session_id=session_id,
        model=selected_model,
    )

# ============================================================================
# OLLAMA INTEGRATION (Simplified)
# ============================================================================

def call_ollama_chat(model: str, message: str, timeout: int = 60) -> str:
    """
    Call Ollama chat endpoint.
    
    In production, integrate with existing modules/nexus_core.py
    to reuse routing, memory, and response planning logic.
    """
    import requests
    
    endpoint = f"{OLLAMA_URL}/api/chat"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": message}],
        "stream": False,
    }
    
    try:
        response = requests.post(endpoint, json=payload, timeout=timeout)
        if response.status_code == 200:
            data = response.json()
            return data.get("message", {}).get("content", "No response from model")
        else:
            raise Exception(f"Ollama returned {response.status_code}")
    except requests.Timeout:
        raise Exception("Ollama request timed out")
    except requests.RequestException as e:
        raise Exception(f"Ollama connection error: {e}")

# ============================================================================
# STARTUP
# ============================================================================

@app.on_event("startup")
async def startup():
    """Initialize on startup."""
    init_db()

# ============================================================================
# RUN
# ============================================================================

if __name__ == "__main__":
    port = int(os.getenv("BACKEND_PORT", 8000))
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="info",
    )
