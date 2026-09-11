# API Contract Discovery: Cognitive Nexus Android Client

## Overview

This document records the **verified** backend API routes and their behavior. The Android client will communicate exclusively with these endpoints.

**Backend Location:** `fullstack-local/backend/app.py` in the original Cognitive Nexus repository
**Ollama Integration:** Local Ollama at `http://localhost:11434` (configurable via `OLLAMA_URL` env var)
**FastAPI Framework:** Yes, uses FastAPI + Uvicorn

---

## Verified Endpoints (v1 MVP)

### 1. **GET /api/health**

**Purpose:** Check backend and Ollama availability

**Status Code:** 200 if OK; varies if errors

**Request:**
```bash
GET /api/health
```

**Response (200 OK):**
```json
{
  "ok": true,
  "chat_model": "llama3.1:8b",
  "time": "2026-09-11T10:30:45.123456"
}
```

**Error Handling:**
- If Ollama is offline: endpoint still returns `{"ok": true}` but `chat_model` may be incorrect
- **Android must check both `ok` field AND verify model availability separately**

**Authentication:** None
**CORS:** Enabled (allow all origins)
**Streaming:** No

---

### 2. **GET /api/models** ⚠️ **MUST BE IMPLEMENTED**

**Purpose:** Get list of available Ollama models for model picker

**Status:** Currently **MISSING** from backend

**Proposed Request:**
```bash
GET /api/models
```

**Proposed Response (200 OK):**
```json
{
  "models": [
    "llama3.1:8b",
    "llama3.2:3b",
    "mistral:7b"
  ],
  "default_model": "llama3.1:8b",
  "ollama_available": true,
  "ollama_url": "http://localhost:11434"
}
```

**Error Response (503 Service Unavailable):**
```json
{
  "error": "Ollama is not running",
  "ollama_available": false,
  "models": [],
  "default_model": null
}
```

**Backend Implementation Note:**
- Must call Ollama's `GET http://localhost:11434/api/tags`
- Rank models using `modules.providers.rank_ollama_models()`
- Return only model names, not full model objects

**Authentication:** None
**CORS:** Enabled
**Streaming:** No

---

### 3. **POST /api/chat**

**Purpose:** Send a user message, get AI response

**Status:** ✅ **EXISTS** and working

**Request:**
```bash
POST /api/chat
Content-Type: application/json

{
  "message": "What is machine learning?",
  "session_id": "user-session-abc123",
  "model": "llama3.1:8b"
}
```

**Response (200 OK):**
```json
{
  "reply": "Machine learning is a branch of AI that...",
  "session_id": "user-session-abc123",
  "model": "llama3.1:8b"
}
```

**Error Response (502 Bad Gateway):**
```json
{
  "detail": "Chat backend error: Connection refused at http://localhost:11434"
}
```

**Request Fields:**
| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| `message` | string | YES | — | Min length 1 |
| `session_id` | string | NO | `"default"` | Groups chat history in SQLite |
| `model` | string | NO | `OLLAMA_CHAT_MODEL` env var or `"llama3.1:8b"` | Ollama model name |

**Response Fields:**
| Field | Type | Notes |
|-------|------|-------|
| `reply` | string | Generated AI response |
| `session_id` | string | Session ID (echoed back) |
| `model` | string | Model used (echoed back or inferred) |

**Backend Behavior:**
1. Stores user message in local SQLite
2. Retrieves recent chat context (last 10 messages)
3. Calls Ollama at `http://localhost:11434/api/chat` with non-streaming request
4. Stores assistant reply in SQLite
5. Returns reply to client

**Authentication:** None
**CORS:** Enabled
**Streaming:** No (v1 only)
**Session Persistence:** YES (SQLite at `backend/local_memory.db`)

---

## Ollama Direct Integration (Not Exposed to Android)

**Android must NOT call Ollama directly.** The backend relays all requests.

**Ollama Endpoints (Backend Only):**
```
GET  http://localhost:11434/api/tags
POST http://localhost:11434/api/chat
```

**Ollama Configuration:**
- URL: `http://localhost:11434` (via `OLLAMA_URL` env var)
- Chat model default: `llama3.1:8b` (via `OLLAMA_CHAT_MODEL` env var)
- Never exposed to public internet
- Session persistence: Local SQLite database

---

## Missing / Out-of-Scope for MVP

| Feature | Status | Reason |
|---------|--------|--------|
| Streaming responses | ❌ Not implemented | Backend uses `stream=False`; can add later |
| Research agents | ❌ Not exposed | Complex backend flow; not mobile-friendly yet |
| Image generation | ❌ Not exposed | Requires ComfyUI/Diffusers; out of scope |
| Web search | ❌ Not exposed | Requires DuckDuckGo integration; future feature |
| Memory/facts | ❌ Not exposed | Internal system; not mobile API |

---

## Network Security

**Production Requirement:** HTTPS only
- Backend must run behind HTTPS reverse proxy (nginx, Caddy, etc.)
- Certificate validation enabled by default on Android

**Development:** HTTP allowed with Android Network Security Config override
- Document exactly which debug build supports cleartext
- Document how to enable (e.g., build variant + manifest override)
- **Never allow cleartext in release builds**

**Ollama Integration:** Always local
- Ollama binds to `127.0.0.1:11434` only (not `0.0.0.0`)
- Backend and Ollama on same machine
- No public internet exposure

---

## Error Codes & Handling

| HTTP | Scenario | Response Body | Android Action |
|------|----------|---------------|----------------|
| 200 | Success | `{"ok": true, ...}` | Display result |
| 422 | Invalid input | `{"detail": "validation error"}` | Show error, highlight field |
| 502 | Ollama offline | `{"detail": "Chat backend error: ..."}` | Show "Backend unavailable" |
| 503 | Service unavailable | `{"detail": "Service temporarily unavailable"}` | Retry with backoff |
| 500 | Server error | `{"detail": "Internal server error"}` | Log and show generic message |

---

## CORS & Allowed Origins

Backend allows all origins:
```python
CORSMiddleware(
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Android:** No special CORS handling needed (mobile requests are not browser requests)

---

## Summary for Android Implementation

**Minimum Required Endpoints:**
1. ✅ `GET /api/health` — Already exists
2. ❌ `GET /api/models` — **Must implement** (provide patch below)
3. ✅ `POST /api/chat` — Already exists

**Request/Response Format:** JSON only
**Authentication:** None (assumes trusted local/private network)
**Sessions:** Via `session_id` parameter (SQLite-backed)
**Model Selection:** User picks from `/api/models` list; passed to `/api/chat`

---

## Backend Patch Required

The following FastAPI endpoint must be added to `fullstack-local/backend/app.py` before Android client is tested:

```python
@app.get("/api/models")
def get_models() -> dict:
    """Return list of available Ollama models."""
    from modules.providers import check_ollama_status, rank_ollama_models, get_ollama_base_url
    
    base_url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    try:
        status = check_ollama_status(base_url=base_url, timeout=2.0)
        models = status.models if status.available else []
        return {
            "models": models,
            "default_model": models[0] if models else CHAT_MODEL,
            "ollama_available": status.available,
            "ollama_url": base_url,
        }
    except Exception as e:
        return {
            "error": str(e),
            "models": [],
            "default_model": None,
            "ollama_available": False,
            "ollama_url": base_url,
        }
```

---

## Assumptions & Constraints

1. **Backend runs locally** on same machine as Ollama (or accessible via private network)
2. **One Ollama instance** per backend deployment
3. **No authentication** (trusted network only)
4. **Sessions are ephemeral** (SQLite database persists messages but not across restarts)
5. **Android has internet access** but does not expose backend to public internet
6. **Models are Ollama-compatible** (standard chat API)

---

## Next Steps

1. ✅ Backend patch: Add `GET /api/models` endpoint
2. 🤖 Android client: Implement Retrofit DTOs and API client
3. 🧪 Test: Verify health → models → chat flow
4. 📱 Deployment: Document backend setup for users

