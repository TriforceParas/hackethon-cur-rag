# Intelligent Multi-Mode Conversational AI Agent

Production-ready FastAPI backend and Streamlit frontend for a conversational AI agent that chooses one mode per request:

- `GENERAL_CHAT`: LLM-only answers.
- `RAG`: answers grounded in uploaded PDF, DOCX, image, text, and common code/config files.
- `WEB_SEARCH`: web search plus LLM summarization for latest/current questions.
- `MEMORY_CONTEXT`: follow-up answers using previous session messages.
- `HYBRID`: agent mode that combines multiple tools, such as document retrieval plus web search.

The project includes a Streamlit chat UI and FastAPI Swagger docs at `/docs`.

## Architecture

Request flow:

```text
User request
-> FastAPI endpoint
-> Agent router
-> GENERAL_CHAT | RAG | WEB_SEARCH | MEMORY_CONTEXT
-> Selected service only
-> Final answer
-> SQLite memory save
-> JSON response
```

The agent orchestrator plans which tools are needed, executes only those tools, and synthesizes the response. It supports single-tool modes and `HYBRID` multi-tool answers. RAG uses sentence-transformer embeddings and a persistent FAISS index. Conversation memory, document metadata, and chunk metadata are stored in SQLite. Image uploads use OCR through `pytesseract` and Pillow.

## Setup

Create and activate a virtual environment, then install dependencies:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create your environment file:

```bash
cp .env.example .env
```

## Environment

```env
APP_NAME=Multi Mode AI Agent
LLM_PROVIDER=groq
OLLAMA_BASE_URL=https://ollama.com
OLLAMA_MODEL=gpt-oss:20b
OLLAMA_THINK=low
OLLAMA_API_KEY=
GROQ_API_KEY=insert-your-groq-api-key-here
GROQ_MODEL=llama-3.1-8b-instant
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
VECTOR_DB=faiss
SQLITE_DB_PATH=./data/app.db
UPLOAD_DIR=./data/uploads
VECTORSTORE_DIR=./data/vectorstore
TOP_K=5
RAG_MIN_SCORE=0.35
WEB_SEARCH_PROVIDER=ollama
DEBUG_ERRORS=false
```

The included `.env` is set for testing Groq `llama-3.1-8b-instant`. Replace the placeholder key:

```env
LLM_PROVIDER=groq
GROQ_API_KEY=your-api-key
```

For Ollama Cloud, use:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=https://ollama.com
OLLAMA_MODEL=gpt-oss:20b
OLLAMA_THINK=low
OLLAMA_API_KEY=your-ollama-cloud-api-key
```

For local Ollama, no API key is normally needed:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_API_KEY=
```

## OCR Support

Image uploads are supported for `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.tiff`, and `.tif`.

Install the Python packages with `requirements.txt`, and install the Tesseract binary on your OS:

```bash
sudo apt install tesseract-ocr
```

Without the Tesseract binary, image upload will return an indexing error explaining that OCR is unavailable.

## Run Ollama

Install Ollama, then pull and run the default model:

```bash
ollama pull llama3.1:8b
ollama serve
```

If you prefer `llama3:8b`, set `OLLAMA_MODEL=llama3:8b`.

## Start FastAPI

```bash
uvicorn app.main:app --reload
```

Open Swagger docs:

```text
http://127.0.0.1:8000/docs
```

## Start Streamlit Frontend

Run the backend in one terminal. For Streamlit, use a separate frontend virtualenv to avoid dependency conflicts with FastAPI/Starlette:

```bash
python3.11 -m venv .venv-streamlit
source .venv-streamlit/bin/activate
pip install -r requirements-frontend.txt
```

Then start the Streamlit UI:

```bash
streamlit run streamlit_app.py
```

The UI opens at:

```text
http://localhost:8501
```

If your API is running somewhere else, set:

```bash
AI_AGENT_API_URL=http://127.0.0.1:8000 streamlit run streamlit_app.py
```

The Streamlit app includes:

- Chat interface
- Session restore by `session_id`
- ChatGPT-style saved chat history using `GET /sessions`
- Document upload, listing, and deletion
- Mode and tool badges
- Source citations
- Demo prompt buttons
- Backend health status

## Example Requests

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Upload a document:

```bash
curl -X POST http://127.0.0.1:8000/documents/upload \
  -F "file=@example.pdf"
```

General chat:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Explain artificial intelligence in simple words"}'
```

RAG question:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Summarize the uploaded document"}'
```

Web search question:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What are the latest AI news today?"}'
```

Memory follow-up:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"demo-session","message":"What is LangGraph?"}'

curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"demo-session","message":"Who created it?"}'
```

List documents:

```bash
curl http://127.0.0.1:8000/documents
```

Session history:

```bash
curl http://127.0.0.1:8000/sessions/demo-session/history
```

Delete a document:

```bash
curl -X DELETE http://127.0.0.1:8000/documents/<document_id>
```

## Notes

- Invalid uploads return `400`.
- Empty chat messages return `400`.
- RAG returns `I could not find this information in the uploaded documents.` when no chunks are available or relevant context is missing.
- Web search failures return `I could not complete web search right now.`
- The app can start without an existing FAISS index; the index is created on first successful document upload.
