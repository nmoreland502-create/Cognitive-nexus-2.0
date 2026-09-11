# Cognitive Nexus API Contract Discovery

## Status: VERIFIED FROM SOURCE + IMPLEMENTED

This document records the **actual verified** backend API routes and behavior for the Android Beta client.

**Backend Location:** `backend_api.py` (feature/android-api-contract)  
**Ollama Integration:** Local HTTP at `http://localhost:11434` (configured via `OLLAMA_URL` env var)  
**Framework:** FastAPI + Uvicorn  
**Database:** SQLite at `data/sessions.db`

---

## Endpoints Implemented and Verified

### 1. GET /api/health

**Purpose:** Check backend and Ollama availability

**Status:** ✅ IMPLEMENTED on feature/android-api-contract

**HTTP Method:** GET  
**Path:** `/api/health`  
**Authentication:** None

**Response (200 OK - both available):**
```json
{
  "ok": true,
  "ollama_available": true,
  "chat_model": "llama3.1:8b",
  "time": "2026-09-11T12:30:45.123456"
}
```

**Response (200 OK - backend ok, Ollama unavailable):**
```json
{
  "ok": false,
  "ollama_available": false,
  "chat_model": null,
  "time": "2026-09-11T12:30:45.123456",
  "detail": "Ollama unavailable or unreachable"
}
```

**HTTP Status:**
- `200`: Backend responding (Ollama status included in body)
- Never raises 503; status always returned

**Implementation:**
- File: `backend_api.py`, function `get_health()`
- Calls: `check_ollama_status(base_url=OLLAMA_URL, timeout=2.0)`
- Never exposes `OLLAMA_URL` value to client
- Safe fields only

**CORS:** Enabled

---

### 2. GET /api/models

**Purpose:** Get list of installed Ollama models

**Status:** ✅ IMPLEMENTED on feature/android-api-contract

**HTTP Method:** GET  
**Path:** `/api/models`  
**Authentication:** None

**Response (200 OK - models available):**
```json
{
  "models": [
    "llama3.1:8b",
    "llama3.2:3b",
    "mistral:7b"
  ],
  "default_model": "llama3.1:8b",
  "ollama_available": true
}
```

**Response (503 Service Unavailable):**
```json
{
  "models": [],
  "default_model": null,
  "ollama_available": false
}
```

**HTTP Status:**
- `200`: Ollama reachable, models returned
- `503`: Ollama unreachable or unavailable

**Implementation:**
- File: `backend_api.py`, function `get_models()`
- Calls: `check_ollama_status()` and `rank_ollama_models()` when available
- Returns model names only (no internal metadata)
- Default model is `CHAT_MODEL` if installed, else first ranked model, else `null`

**CORS:** Enabled

---

### 3. GET /api/conversations

**Purpose:** Get list of active conversations

**Status:** ✅ IMPLEMENTED on feature/android-api-contract

**HTTP Method:** GET  
**Path:** `/api/conversations`  
**Authentication:** None

**Response (200 OK):**
```json
[
  {
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "created_at": "2026-09-11T10:00:00.000000",
    "updated_at": "2026-09-11T12:30:00.000000",
    "title": null,
    "message_count": 5
  },
  {
    "session_id": "550e8400-e29b-41d4-a716-446655440001",
    "created_at": "2026-09-11T11:00:00.000000",
    "updated_at": "2026-09-11T12:00:00.000000",
    "title": "Research Questions",
    "message_count": 12
  }
]
```

**Implementation:**
- File: `backend_api.py`, function `list_conversations()`
- Queries SQLite `conversations` table (excludes `deleted_at IS NOT NULL`)
- Ordered by `updated_at DESC`
- Includes message count per session

**Storage:**
- Table: `conversations` (session_id, created_at, updated_at, title, deleted_at)

---

### 4. POST /api/conversations

**Purpose:** Create a new conversation/session

**Status:** ✅ IMPLEMENTED on feature/android-api-contract

**HTTP Method:** POST  
**Path:** `/api/conversations`  
**Authentication:** None  
**Request Body:** Empty `{}`

**Response (200 OK):**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440002",
  "created_at": "2026-09-11T12:31:00.000000",
  "updated_at": "2026-09-11T12:31:00.000000"
}
```

**Implementation:**
- File: `backend_api.py`, function `create_conversation()`
- Generates UUID `session_id`
- Records creation timestamp
- Returns session metadata

---

### 5. GET /api/conversations/{session_id}/messages

**Purpose:** Get message history for a conversation

**Status:** ✅ IMPLEMENTED on feature/android-api-contract

**HTTP Method:** GET  
**Path:** `/api/conversations/{session_id}/messages`  
**Authentication:** None

**Response (200 OK):**
```json
[
  {
    "role": "user",
    "content": "What is machine learning?",
    "model": "llama3.1:8b",
    "created_at": "2026-09-11T12:00:00.000000"
  },
  {
    "role": "assistant",
    "content": "Machine learning is a subset of AI where systems learn from data...",
    "model": "llama3.1:8b",
    "created_at": "2026-09-11T12:00:02.000000"
  }
]
```

**HTTP Status:**
- `200`: Session exists and is active
- `404`: Session not found or marked deleted

**Implementation:**
- File: `backend_api.py`, function `get_conversation_messages()`
- Queries SQLite `messages` table ordered by `created_at ASC`
- Validates session exists and `deleted_at IS NULL`

---

### 6. DELETE /api/conversations/{session_id}

**Purpose:** Delete (soft-delete) a conversation

**Status:** ✅ IMPLEMENTED on feature/android-api-contract

**HTTP Method:** DELETE  
**Path:** `/api/conversations/{session_id}`  
**Authentication:** None

**Response (200 OK):**
```json
{
  "status": "deleted",
  "session_id": "550e8400-e29b-41d4-a716-446655440002"
}
```

**HTTP Status:**
- `200`: Deletion successful
- `404`: Session not found

**Implementation:**
- File: `backend_api.py`, function `delete_conversation()`
- Soft-delete: sets `deleted_at` to current timestamp
- Does not physically erase messages
- Subsequent `GET /api/conversations/{session_id}/messages` returns 404

---

### 7. POST /api/chat

**Purpose:** Send a message and receive AI response

**Status:** ✅ IMPLEMENTED on feature/android-api-contract

**HTTP Method:** POST  
**Path:** `/api/chat`  
**Content-Type:** application/json  
**Authentication:** None

**Request:**
```json
{
  "message": "What is Cognitive Nexus?",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "model": "llama3.1:8b"
}
```

**Request Fields:**
| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| `message` | string | YES | — | Min length 1 |
| `session_id` | string | NO | UUID generated | Session ID; creates session if missing |
| `model` | string | NO | `CHAT_MODEL` env var | Must be installed on Ollama |

**Response (200 OK):**
```json
{
  "reply": "Cognitive Nexus is a reality-first AI research platform...",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "model": "llama3.1:8b"
}
```

**Error Responses:**

**422 Unprocessable Entity** (invalid message):
```json
{
  "detail": "Message cannot be empty"
}
```

**400 Bad Request** (model not installed):
```json
{
  "detail": "Model 'nonexistent-model' is not installed on the backend"
}
```

**503 Service Unavailable** (Ollama offline):
```json
{
  "detail": "Ollama is unavailable"
}
```

**504 Gateway Timeout** (Ollama timeout):
```json
{
  "detail": "Failed to get response from Ollama"
}
```

**HTTP Status:**
- `200`: Message sent, response received
- `400`: Selected model not installed
- `422`: Validation error (empty message)
- `503`: Ollama unavailable
- `504`: Ollama timeout/connection error

**Implementation:**
- File: `backend_api.py`, function `chat()`
- Creates or reuses `session_id`
- Stores user message to SQLite `messages` table
- Validates selected model against installed models
- Calls Ollama via `call_ollama_chat(model, message)`
- Stores assistant response
- Updates `conversations.updated_at`
- Returns safe reply without raw error exposure

**Behavior:**
- Backward compatible: existing clients without `model` field continue using default
- Model selection is optional and validated
- Non-streaming in v1 (stream=False)
- Fallback model is `CHAT_MODEL` environment variable

**CORS:** Enabled

---

## Database Schema

### conversations table
```sql
CREATE TABLE conversations (
  session_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  title TEXT,
  deleted_at TEXT
);
```

### messages table
```sql
CREATE TABLE messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  role TEXT NOT NULL,           -- "user" or "assistant"
  content TEXT NOT NULL,
  model TEXT,                   -- Model used for response
  created_at TEXT NOT NULL,
  FOREIGN KEY (session_id) REFERENCES conversations(session_id)
);
```

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama endpoint |
| `OLLAMA_CHAT_MODEL` | `llama3.1:8b` | Default chat model |
| `BACKEND_PORT` | `8000` | FastAPI server port |

---

## Network Security

**Production:**
- HTTPS only
- TLS certificate validation required
- Ollama binds to `127.0.0.1:11434` only (not public internet)

**Development (trusted home Wi-Fi):**
- HTTP allowed over local network
- Android Network Security Config overrides certificate validation for debug builds only

**Ollama:**
- Never exposed to public internet
- Backend relays all requests; Android never calls Ollama directly

---

## Error Handling & Validation

| HTTP | Scenario | Body | Android Action |
|------|----------|------|----------------|
| 200 | Success | JSON response | Display result |
| 400 | Invalid model | `{"detail": "Model not installed"}` | Show error, prompt retry |
| 422 | Validation | `{"detail": "Message cannot be empty"}` | Highlight field, retry |
| 503 | Ollama offline | `{"detail": "Ollama is unavailable"}` | Show "Ollama offline", suggest check backend |
| 504 | Timeout | `{"detail": "Failed to get response"}` | Show timeout, retry with backoff |
| 500 | Server error | `{"detail": "Internal server error"}` | Log, show generic message |

---

## Backward Compatibility

- Existing chat clients sending only `message` and `session_id` continue to work unchanged
- Default model is `OLLAMA_CHAT_MODEL` environment variable
- Model validation is transparent
- SQLite session persistence is preserved

---

## Features NOT in v1 (Deferred)

| Feature | Reason |
|---------|--------|
| Streaming responses | Requires SSE/WebSocket; non-streaming v1 works reliably |
| Research agents | Complex multi-step workflows; needs dedicated API |
| Web search | Requires backend integration; defer to v2 |
| Image generation | Requires ComfyUI/Diffusers; out of scope |
| Memory/facts | Internal system; not mobile API |
| Real-time typing | Streaming required; defer to v2 |

---

## Testing Commands

### Test Health Endpoint
```bash
curl -X GET http://localhost:8000/api/health
```

### Test Models Endpoint
```bash
curl -X GET http://localhost:8000/api/models
```

### Create Conversation
```bash
curl -X POST http://localhost:8000/api/conversations
```

### Get Conversations
```bash
curl -X GET http://localhost:8000/api/conversations
```

### Get Messages
```bash
curl -X GET http://localhost:8000/api/conversations/{session_id}/messages
```

### Send Chat Message (default model)
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello, what is Ollama?",
    "session_id": "test-session-123"
  }'
```

### Send Chat Message (selected model)
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain machine learning.",
    "session_id": "test-session-123",
    "model": "mistral:7b"
  }'
```

### Delete Conversation
```bash
curl -X DELETE http://localhost:8000/api/conversations/{session_id}
```

---

## Running the Backend

### Prerequisites
- Python 3.8+
- FastAPI: `pip install fastapi uvicorn`
- Requests: `pip install requests`
- Ollama running at `http://localhost:11434`
- At least one Ollama model installed

### Start Backend
```bash
python backend_api.py
```

Server listens on `http://localhost:8000`

### Environment Setup (Optional)
```bash
export OLLAMA_URL=http://localhost:11434
export OLLAMA_CHAT_MODEL=llama3.1:8b
export BACKEND_PORT=8000
python backend_api.py
```

---

## Notes for Android Client

1. **No Raw Ollama Calls:** Android never calls Ollama directly. All requests go through `/api/chat`.
2. **Safe Error Messages:** Backend never returns stack traces, raw exception text, or internal URLs to Android.
3. **Model Validation:** Model selection is safe—invalid models are rejected with a clear message.
4. **Session Persistence:** SQLite backs all sessions. Conversations survive backend restarts.
5. **Soft Delete:** Conversations are soft-deleted (marked, not erased). This allows recovery if needed.

---

## Summary for Android Implementation

**Minimum Required Endpoints:**
1. ✅ `GET /api/health` — Backend and Ollama status
2. ✅ `GET /api/models` — Installed models list
3. ✅ `POST /api/conversations` — Create new chat session
4. ✅ `GET /api/conversations` — List existing chats
5. ✅ `GET /api/conversations/{session_id}/messages` — Conversation history
6. ✅ `DELETE /api/conversations/{session_id}` — Delete chat
7. ✅ `POST /api/chat` — Send message, get response

**Request/Response Format:** JSON only  
**Authentication:** None (private network; future: add token/HMAC if remote)  
**CORS:** Fully enabled for development and home-network use

---

**Last Updated:** 2026-09-11  
**Branch:** feature/android-api-contract  
**Status:** Complete and ready for Android implementation
