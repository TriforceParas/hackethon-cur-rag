# API Design Guide for Frontend Integration

This document is for the frontend team integrating the FastAPI backend into a MERN stack application.

Backend base URL during local development:

```text
http://127.0.0.1:8000
```

Swagger/OpenAPI docs:

```text
http://127.0.0.1:8000/docs
```

## Product Behavior

The backend exposes an intelligent conversational AI API. The frontend sends user messages to `/chat`; the backend decides the best mode:

- `RAG`: search uploaded documents first and answer from document context.
- `WEB_SEARCH`: use web search for latest/current/live questions. The backend uses Ollama Web Search by default when `WEB_SEARCH_PROVIDER=ollama`.
- `GENERAL_CHAT`: normal LLM answer.
- `MEMORY_CONTEXT`: follow-up answer using previous session messages.
- `HYBRID`: combine multiple tools, such as uploaded documents plus current web results.

Current behavior is document-first:

1. If uploaded documents exist, the backend first searches those documents.
2. If relevant chunks are found, response mode is `RAG`.
3. If documents do not contain relevant information, the backend falls back to general chat or web search.

The frontend does not need to decide which AI tool to call.

## Content Type Summary

| Endpoint | Method | Content Type |
|---|---:|---|
| `/health` | `GET` | none |
| `/chat` | `POST` | `application/json` |
| `/documents/upload` | `POST` | `multipart/form-data` |
| `/documents` | `GET` | none |
| `/documents/{document_id}` | `DELETE` | none |
| `/sessions` | `GET` | none |
| `/sessions/{session_id}/history` | `GET` | none |

## Endpoints

### Health Check

```http
GET /health
```

Response:

```json
{
  "status": "ok"
}
```

Use this to show backend availability in development or admin screens.

## Chat

```http
POST /chat
Content-Type: application/json
```

Request:

```json
{
  "session_id": "optional-session-id",
  "message": "Tell me the details about the hackathon"
}
```

Fields:

| Field | Type | Required | Notes |
|---|---|---:|---|
| `session_id` | `string \| null` | No | If omitted, backend creates a new session UUID. Store it in frontend state/local storage. |
| `message` | `string` | Yes | User message. Empty messages return `400`. |

Response:

```json
{
  "session_id": "623d5c19-1995-40ec-a412-a242efe08786",
  "mode": "RAG",
  "answer": "The hackathon details are...",
  "sources": [
    {
      "filename": "hackathon.pdf",
      "chunk_id": "a1b2c3",
      "page_number": 2,
      "similarity_score": 0.72
    }
  ],
  "memory_used": false,
  "tools_used": ["rag"]
}
```

Possible `mode` values:

```ts
type ChatMode = "GENERAL_CHAT" | "RAG" | "WEB_SEARCH" | "MEMORY_CONTEXT" | "HYBRID";
```

Frontend behavior:

- Always keep the returned `session_id`.
- Render `answer` as the assistant message.
- Show `mode` as a small debug/status badge if useful.
- If `sources` is not empty, show citations below the answer.
- For `RAG`, sources include uploaded file metadata.
- For `WEB_SEARCH`, sources include web titles and URLs.
- For `HYBRID`, sources can contain both document and web citations. Each source includes a `tool` field when available.

Example web search response source:

```json
{
  "title": "Example News Title",
  "url": "https://example.com/article"
}
```

### Chat UI Flow

Recommended frontend state:

```ts
type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  mode?: "GENERAL_CHAT" | "RAG" | "WEB_SEARCH" | "MEMORY_CONTEXT";
  sources?: Source[];
  toolsUsed?: string[];
  createdAt?: string;
};

type Source = {
  tool?: "rag" | "web_search";
  filename?: string;
  chunk_id?: string;
  page_number?: number | null;
  similarity_score?: number;
  title?: string;
  url?: string;
};
```

Example frontend request with `fetch`:

```ts
const res = await fetch(`${API_BASE_URL}/chat`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    session_id: sessionId,
    message: userMessage,
  }),
});

if (!res.ok) {
  throw new Error("Chat request failed");
}

const data = await res.json();
setSessionId(data.session_id);
```

## Upload Document

```http
POST /documents/upload
Content-Type: multipart/form-data
```

Supported file types:

- PDF: `.pdf`
- Word: `.docx`
- Images with OCR: `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.tiff`, `.tif`
- Text/code/config files: `.txt`, `.md`, `.csv`, `.json`, `.xml`, `.html`, `.log`, `.py`, `.js`, `.ts`, `.java`, `.c`, `.cpp`, `.yaml`, `.yml`, etc.

Request field:

| Field | Type | Required |
|---|---|---:|
| `file` | `File` | Yes |

Response:

```json
{
  "document_id": "8b7205a7-97cc-4d41-b7f4-54a7b0d7f47f",
  "filename": "hackathon.pdf",
  "chunks_created": 25,
  "status": "indexed"
}
```

Frontend upload example:

```ts
const formData = new FormData();
formData.append("file", selectedFile);

const res = await fetch(`${API_BASE_URL}/documents/upload`, {
  method: "POST",
  body: formData,
});

if (!res.ok) {
  const error = await res.json();
  throw new Error(error.detail || "Upload failed");
}

const uploadedDocument = await res.json();
```

Important frontend UX notes:

- Upload may take time because OCR, embedding generation, and vector indexing happen during the request.
- Show a loading state like “Indexing document...”.
- The first document upload may be slower because the embedding model downloads/loads.
- After upload succeeds, the user can ask natural questions like:

```text
Tell me the details about the hackathon
```

They do not need to type “uploaded document” every time.

## List Documents

```http
GET /documents
```

Response:

```json
[
  {
    "document_id": "8b7205a7-97cc-4d41-b7f4-54a7b0d7f47f",
    "filename": "hackathon.pdf",
    "created_at": "2026-06-06 09:42:12"
  }
]
```

Use this to render an uploaded documents panel.

## Delete Document

```http
DELETE /documents/{document_id}
```

Response:

```json
{
  "document_id": "8b7205a7-97cc-4d41-b7f4-54a7b0d7f47f",
  "status": "deleted"
}
```

Frontend behavior:

- Remove the document from UI after success.
- If deletion returns `404`, document no longer exists.

## Session History

```http
GET /sessions?limit=50
```

Response:

```json
[
  {
    "session_id": "623d5c19-1995-40ec-a412-a242efe08786",
    "title": "What are the hackathon details?",
    "message_count": 4,
    "last_mode": "RAG",
    "created_at": "2026-06-06 09:50:00",
    "updated_at": "2026-06-06 09:52:10"
  }
]
```

Use this to build ChatGPT-style saved chat history. Clicking one session should call the history endpoint below.

```http
GET /sessions/{session_id}/history
```

Response:

```json
{
  "session_id": "623d5c19-1995-40ec-a412-a242efe08786",
  "messages": [
    {
      "role": "user",
      "content": "What is LangGraph?",
      "created_at": "2026-06-06 09:50:00"
    },
    {
      "role": "assistant",
      "content": "LangGraph is...",
      "created_at": "2026-06-06 09:50:04"
    }
  ]
}
```

Use this when restoring a chat page from an existing `session_id`.

## Error Handling

Common error shapes:

```json
{
  "detail": "Message cannot be empty"
}
```

```json
{
  "detail": "Unsupported file type. Upload PDF, DOCX, images, or common text/code files."
}
```

Recommended frontend handling:

- For `400`, show the backend `detail`.
- For `404`, show “Not found” or refresh the relevant list.
- For `500`, show a general retry message and log the detail in development.
- `/chat` may return HTTP `200` with an answer explaining that LLM/web/RAG failed gracefully. Render the answer normally.

## MERN Integration Notes

Recommended environment variable in React/Next frontend:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

or for Next.js:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

Recommended API helper:

```ts
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
```

If the MERN backend proxies requests to FastAPI:

```text
React -> Express API -> FastAPI AI API
```

then Express should forward:

- `POST /chat`
- `POST /documents/upload`
- `GET /documents`
- `DELETE /documents/:documentId`
- `GET /sessions/:sessionId/history`

For file upload proxying, use multipart middleware carefully. The simpler approach is often:

```text
React -> FastAPI directly for uploads
React -> Express for app/user auth
```

If authentication is added later, the frontend should send:

```http
Authorization: Bearer <jwt>
```

The current backend does not enforce auth yet.

## AI Agent Integration Notes

If the frontend team uses an AI coding agent to integrate this backend, give it these instructions:

```text
Integrate a FastAPI AI backend into our MERN frontend.
Base URL is configurable through VITE_API_BASE_URL or NEXT_PUBLIC_API_BASE_URL.
Use POST /chat for all user messages.
Persist returned session_id in frontend state and localStorage.
Use POST /documents/upload with multipart/form-data field name "file".
Render sources returned by /chat below assistant answers.
Do not decide AI mode in frontend; backend returns mode.
Show upload/indexing loading state because document indexing can take time.
Support response modes: GENERAL_CHAT, RAG, WEB_SEARCH, MEMORY_CONTEXT.
```

## Suggested Frontend Screens

- Chat screen with message list, input box, send button, and loading state.
- Document upload panel with file picker and indexed document list.
- Source citation component for RAG/web answers.
- Optional session history restore using `session_id`.
- Optional backend status indicator using `/health`.

## End-to-End Test Script

1. Start backend.
2. Open `/docs`.
3. `GET /health`.
4. Upload `hackathon.pdf` using `/documents/upload`.
5. Ask:

```json
{
  "message": "Tell me the details about the hackathon"
}
```

Expected:

```json
{
  "mode": "RAG",
  "sources": [
    {
      "filename": "hackathon.pdf"
    }
  ]
}
```

6. Ask:

```json
{
  "message": "What are the latest AI news today?"
}
```

Expected:

```json
{
  "mode": "WEB_SEARCH"
}
```

7. Ask two messages with the same session:

```json
{
  "session_id": "demo-session",
  "message": "What is LangGraph?"
}
```

```json
{
  "session_id": "demo-session",
  "message": "Who created it?"
}
```

Expected:

```json
{
  "memory_used": true
}
```
