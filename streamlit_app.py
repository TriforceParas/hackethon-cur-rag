import os
import uuid
from html import escape
from typing import Any

import requests
import streamlit as st


DEFAULT_API_BASE_URL = os.getenv("AI_AGENT_API_URL", "http://127.0.0.1:8000")

SUPPORTED_UPLOAD_TYPES = [
    "pdf",
    "docx",
    "txt",
    "md",
    "csv",
    "json",
    "xml",
    "html",
    "htm",
    "log",
    "py",
    "js",
    "ts",
    "java",
    "c",
    "cpp",
    "h",
    "hpp",
    "cs",
    "go",
    "rs",
    "php",
    "rb",
    "yaml",
    "yml",
    "ini",
    "conf",
    "jpg",
    "jpeg",
    "png",
    "webp",
    "bmp",
    "tiff",
    "tif",
]

MODE_LABELS = {
    "GENERAL_CHAT": "General Chat",
    "RAG": "Document RAG",
    "WEB_SEARCH": "Web Search",
    "MEMORY_CONTEXT": "Memory",
    "HYBRID": "Hybrid Agent",
}

PAGES = ["Chat", "Documents", "History", "Settings"]
PAGE_LABELS = {"Chat": "Chat", "Documents": "Upload", "History": "History", "Settings": "⚙ Settings"}


def init_state() -> None:
    defaults = {
        "api_base_url": DEFAULT_API_BASE_URL,
        "session_id": None,
        "messages": [],
        "documents_cache": [],
        "sessions_cache": [],
        "backend_ok": None,
        "last_error": None,
        "page": "Chat",
        "nav_page": "Chat",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def normalize_base_url(url: str) -> str:
    return url.strip().rstrip("/")


def api_url(path: str) -> str:
    return f"{normalize_base_url(st.session_state.api_base_url)}{path}"


def api_request(method: str, path: str, **kwargs: Any) -> Any:
    try:
        response = requests.request(method, api_url(path), timeout=120, **kwargs)
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not reach backend: {exc}") from exc

    if not response.ok:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise RuntimeError(detail or f"Request failed with status {response.status_code}")

    if response.content:
        return response.json()
    return None


def check_backend() -> bool:
    try:
        data = api_request("GET", "/health")
        ok = data == {"status": "ok"}
        st.session_state.backend_ok = ok
        st.session_state.last_error = None
        return ok
    except RuntimeError as exc:
        st.session_state.backend_ok = False
        st.session_state.last_error = str(exc)
        return False


def fetch_documents() -> list[dict[str, Any]]:
    try:
        docs = api_request("GET", "/documents")
        st.session_state.documents_cache = docs or []
        return st.session_state.documents_cache
    except RuntimeError as exc:
        st.session_state.last_error = str(exc)
        return st.session_state.documents_cache


def fetch_sessions(limit: int = 30) -> list[dict[str, Any]]:
    try:
        sessions = api_request("GET", f"/sessions?limit={limit}")
        st.session_state.sessions_cache = sessions or []
        return st.session_state.sessions_cache
    except RuntimeError as exc:
        st.session_state.last_error = str(exc)
        return st.session_state.sessions_cache


def load_session_history(session_id: str) -> None:
    data = api_request("GET", f"/sessions/{session_id}/history")
    st.session_state.session_id = data["session_id"]
    st.session_state.messages = [
        {
            "id": str(uuid.uuid4()),
            "role": item["role"],
            "content": item["content"],
            "created_at": item.get("created_at"),
            "mode": item.get("mode"),
            "sources": [],
            "tools_used": [],
            "memory_used": False,
        }
        for item in data.get("messages", [])
    ]


def new_chat() -> None:
    st.session_state.session_id = None
    st.session_state.messages = []
    st.session_state.last_error = None


def send_message(message: str) -> None:
    st.session_state.messages.append(
        {
            "id": str(uuid.uuid4()),
            "role": "user",
            "content": message,
            "mode": None,
            "sources": [],
            "tools_used": [],
            "memory_used": False,
        }
    )

    payload = {"message": message}
    if st.session_state.session_id:
        payload["session_id"] = st.session_state.session_id

    try:
        data = api_request("POST", "/chat", json=payload)
    except RuntimeError as exc:
        st.session_state.messages.append(
            {
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": f"Backend error: {exc}",
                "mode": "ERROR",
                "sources": [],
                "tools_used": [],
                "memory_used": False,
            }
        )
        return

    st.session_state.session_id = data["session_id"]
    st.session_state.messages.append(
        {
            "id": str(uuid.uuid4()),
            "role": "assistant",
            "content": data.get("answer", ""),
            "mode": data.get("mode"),
            "sources": data.get("sources", []),
            "tools_used": data.get("tools_used", []),
            "memory_used": data.get("memory_used", False),
        }
    )
    fetch_sessions()


def session_title(session: dict[str, Any], max_length: int = 42) -> str:
    title = " ".join(str(session.get("title") or "New conversation").split())
    if len(title) > max_length:
        return f"{title[:max_length - 3].rstrip()}..."
    return title


def upload_file(uploaded_file: Any) -> dict[str, Any]:
    files = {
        "file": (
            uploaded_file.name,
            uploaded_file.getvalue(),
            uploaded_file.type or "application/octet-stream",
        )
    }
    return api_request("POST", "/documents/upload", files=files)


def delete_document(document_id: str) -> None:
    api_request("DELETE", f"/documents/{document_id}")
    fetch_documents()


def inject_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg: #0c111d;
            --panel: #111827;
            --panel-2: #151f31;
            --panel-3: #1f2937;
            --ink: #f8fafc;
            --muted: #a7b0c0;
            --line: #2b3648;
            --accent: #38bdf8;
            --accent-2: #22c55e;
            --accent-soft: rgba(56, 189, 248, 0.12);
            --ok: #34d399;
            --warn: #f59e0b;
            --danger: #fb7185;
        }

        html, body, [data-testid="stAppViewContainer"] {
            background: var(--bg);
            color: var(--ink);
        }

        [data-testid="stAppViewContainer"] > .main {
            background:
                radial-gradient(circle at 18% 0%, rgba(56, 189, 248, 0.10), transparent 24rem),
                radial-gradient(circle at 82% 12%, rgba(34, 197, 94, 0.08), transparent 28rem),
                var(--bg);
        }

        .block-container {
            padding-top: 1.6rem;
            padding-bottom: 2rem;
            max-width: 1240px;
        }

        [data-testid="stSidebar"] {
            background: #0f172a;
            border-right: 1px solid var(--line);
        }

        [data-testid="stSidebar"] * {
            color: var(--ink);
        }

        [data-testid="stSidebar"] .stCaptionContainer,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] p {
            color: var(--muted) !important;
        }

        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 {
            color: var(--ink) !important;
            font-weight: 750;
        }

        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea,
        [data-baseweb="input"] input {
            background: #0b1220 !important;
            color: var(--ink) !important;
            border-color: var(--line) !important;
        }

        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
            background: #0b1220;
            border: 1px dashed #41506a;
            border-radius: 8px;
        }

        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] * {
            color: var(--muted) !important;
        }

        .stButton > button {
            border-radius: 8px;
            border: 1px solid #334155;
            background: #182235;
            color: var(--ink);
            min-height: 40px;
            font-weight: 650;
        }

        .stButton > button:hover {
            border-color: var(--accent);
            color: var(--ink);
            background: #1e2b44;
        }

        .stButton > button:disabled {
            opacity: 0.42;
        }

        .nav-strip {
            margin-bottom: 14px;
        }

        .nav-brand {
            color: var(--ink);
            font-weight: 800;
            font-size: 18px;
            padding-top: 8px;
            white-space: nowrap;
        }

        .stAlert {
            border-radius: 8px;
        }

        hr {
            border-color: var(--line) !important;
        }

        .app-header {
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 22px 24px;
            background:
                linear-gradient(135deg, rgba(56, 189, 248, 0.16), rgba(34, 197, 94, 0.06)),
                linear-gradient(180deg, #121c2e 0%, #0f172a 100%);
            box-shadow: 0 18px 60px rgba(0, 0, 0, 0.22);
            margin-bottom: 18px;
        }

        .app-title {
            font-size: 32px;
            font-weight: 800;
            color: var(--ink);
            margin: 0;
            letter-spacing: 0;
        }

        .app-subtitle {
            color: var(--muted);
            font-size: 15px;
            margin-top: 8px;
            max-width: 880px;
            line-height: 1.55;
        }

        .status-row {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 12px;
        }

        .badge {
            display: inline-flex;
            align-items: center;
            border: 1px solid #334155;
            border-radius: 999px;
            padding: 5px 10px;
            font-size: 12px;
            color: #dbeafe;
            background: rgba(15, 23, 42, 0.78);
            line-height: 1.2;
        }

        .badge.mode {
            border-color: rgba(56, 189, 248, 0.46);
            color: #7dd3fc;
            background: var(--accent-soft);
        }

        .badge.memory {
            border-color: rgba(52, 211, 153, 0.42);
            color: var(--ok);
            background: rgba(20, 184, 166, 0.11);
        }

        .badge.error {
            border-color: rgba(251, 113, 133, 0.42);
            color: var(--danger);
            background: rgba(251, 113, 133, 0.10);
        }

        .metric-card {
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 16px 18px;
            background: linear-gradient(180deg, #111827 0%, #0f172a 100%);
            min-height: 92px;
        }

        .metric-label {
            color: var(--muted);
            font-size: 13px;
            font-weight: 650;
            margin-bottom: 10px;
        }

        .metric-value {
            color: var(--ink);
            font-size: 28px;
            font-weight: 800;
            line-height: 1;
        }

        .metric-hint {
            color: #7dd3fc;
            font-size: 12px;
            margin-top: 8px;
        }

        .empty-state {
            border: 1px solid #1e3a5f;
            border-radius: 8px;
            padding: 18px 20px;
            background: linear-gradient(135deg, rgba(14, 165, 233, 0.18), rgba(15, 23, 42, 0.82));
            color: #bfdbfe;
            margin-top: 12px;
            margin-bottom: 12px;
        }

        .notice {
            border-radius: 8px;
            padding: 12px 13px;
            margin: 12px 0;
            font-size: 13px;
            font-weight: 650;
        }

        .notice.ok {
            border: 1px solid rgba(52, 211, 153, 0.35);
            background: rgba(20, 184, 166, 0.12);
            color: var(--ok);
        }

        .notice.error {
            border: 1px solid rgba(251, 113, 133, 0.36);
            background: rgba(251, 113, 133, 0.10);
            color: var(--danger);
        }

        .section-label {
            color: var(--muted);
            font-size: 13px;
            font-weight: 700;
            margin: 10px 0 8px;
        }

        .source-card {
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 10px 12px;
            margin-bottom: 8px;
            background: #0f172a;
        }

        .source-title {
            font-weight: 650;
            color: var(--ink);
            font-size: 14px;
        }

        .source-meta {
            color: var(--muted);
            font-size: 12px;
            margin-top: 4px;
            overflow-wrap: anywhere;
        }

        .doc-row {
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 10px;
            background: #111827;
            margin-bottom: 8px;
        }

        .doc-name {
            font-weight: 650;
            font-size: 13px;
            color: var(--ink);
            overflow-wrap: anywhere;
        }

        .doc-meta {
            font-size: 12px;
            color: var(--muted);
            margin-top: 2px;
        }

        .stChatMessage {
            border-radius: 8px;
        }

        [data-testid="stChatMessage"] {
            background: rgba(17, 24, 39, 0.72);
            border: 1px solid var(--line);
        }

        [data-testid="stChatInput"] {
            background: rgba(15, 23, 42, 0.96);
            border-top: 1px solid var(--line);
        }

        [data-testid="stChatInput"] textarea {
            background: #151c2d !important;
            color: var(--ink) !important;
            border: 1px solid #334155 !important;
            border-radius: 8px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    session_text = escape(st.session_state.session_id or "Not started")
    status_label = "Online" if st.session_state.backend_ok else "Needs backend"
    status_class = "memory" if st.session_state.backend_ok else "error"
    page = escape(PAGE_LABELS.get(st.session_state.page, st.session_state.page).replace("⚙ ", ""))
    st.markdown(
        f"""
        <div class="app-header">
            <p class="app-title">{page}</p>
            <div class="app-subtitle">
                Source-aware agent console for chat, document RAG, web search, memory, and hybrid tool orchestration.
            </div>
            <div class="status-row">
                <span class="badge {status_class}">Backend: {status_label}</span>
                <span class="badge">Session: {session_text}</span>
                <span class="badge">Agent modes: General, RAG, Web, Memory, Hybrid</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_navbar() -> None:
    if st.session_state.page not in PAGES:
        st.session_state.page = "Chat"

    active_page = st.session_state.page
    st.markdown('<div class="nav-strip">', unsafe_allow_html=True)
    cols = st.columns([3.6, 1, 1, 1, 1], gap="small")
    with cols[0]:
        st.markdown('<div class="nav-brand">Multi-Mode AI Agent</div>', unsafe_allow_html=True)

    for col, page in zip(cols[1:], PAGES, strict=True):
        with col:
            if st.button(
                PAGE_LABELS.get(page, page),
                key=f"top-nav-{page}",
                type="primary" if active_page == page else "secondary",
                use_container_width=True,
            ):
                st.session_state.page = page
                st.session_state.nav_page = page
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def render_source(source: dict[str, Any], index: int) -> None:
    tool = escape(str(source.get("tool", "")))
    if source.get("url"):
        title = escape(str(source.get("title") or f"Web source {index}"))
        meta = escape(str(source["url"]))
    else:
        title = escape(str(source.get("filename") or f"Document source {index}"))
        page = f"page {source['page_number']}" if source.get("page_number") else "page unavailable"
        score = source.get("similarity_score")
        score_text = f", score {score:.3f}" if isinstance(score, (float, int)) else ""
        meta = escape(f"{page}{score_text}")

    tool_text = f"Tool: {tool}" if tool else "Source"
    st.markdown(
        f"""
        <div class="source-card">
            <div class="source-title">{index}. {title}</div>
            <div class="source-meta">{tool_text} | {meta}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_message_meta(message: dict[str, Any]) -> None:
    if message["role"] != "assistant":
        return

    mode = message.get("mode")
    tools = message.get("tools_used") or []
    memory_used = message.get("memory_used")
    badges = []
    if mode:
        label = MODE_LABELS.get(mode, mode)
        css_class = "error" if mode == "ERROR" else "mode"
        badges.append(f'<span class="badge {css_class}">{label}</span>')
    for tool in tools:
        badges.append(f'<span class="badge">Tool: {tool}</span>')
    if memory_used:
        badges.append('<span class="badge memory">Memory used</span>')

    if badges:
        st.markdown(f'<div class="status-row">{"".join(badges)}</div>', unsafe_allow_html=True)

    sources = message.get("sources") or []
    if sources:
        with st.expander(f"Sources ({len(sources)})", expanded=False):
            for index, source in enumerate(sources, start=1):
                render_source(source, index)


def render_chat() -> None:
    if not st.session_state.messages:
        st.markdown(
            """
            <div class="empty-state">
                Upload a document, choose a demo prompt, or ask a fresh question. The agent will pick the right tools automatically.
            </div>
            """,
            unsafe_allow_html=True,
        )

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"] or "_No answer returned._")
            render_message_meta(message)

    prompt = st.chat_input("Ask about your documents, latest news, or anything general")
    if prompt:
        with st.spinner("Agent is planning tools and generating an answer..."):
            send_message(prompt)
        st.rerun()


def render_chat_page() -> None:
    render_chat()


def render_quick_prompts() -> None:
    st.markdown('<div class="section-label">Demo prompts</div>', unsafe_allow_html=True)
    cols = st.columns(4)
    prompts = [
        "Explain artificial intelligence in simple words",
        "What are today's AI news?",
        "What are the hackathon details?",
        "Compare the uploaded document with latest AI trends",
    ]
    for col, prompt in zip(cols, prompts, strict=True):
        with col:
            if st.button(prompt, use_container_width=True):
                with st.spinner("Agent is working..."):
                    send_message(prompt)
                st.rerun()


def render_documents_page() -> None:
    render_header()
    docs = fetch_documents()

    left, right = st.columns([0.95, 1.05], gap="large")
    with left:
        st.markdown('<div class="section-label">Upload knowledge files</div>', unsafe_allow_html=True)
        uploaded_files = st.file_uploader(
            "Choose files for indexing",
            type=SUPPORTED_UPLOAD_TYPES,
            accept_multiple_files=True,
            help="PDF, DOCX, images for OCR, text, code, and config files are supported.",
        )
        if uploaded_files and st.button("Index selected files", use_container_width=True):
            progress = st.progress(0)
            for index, uploaded_file in enumerate(uploaded_files, start=1):
                with st.spinner(f"Indexing {uploaded_file.name}..."):
                    try:
                        result = upload_file(uploaded_file)
                        st.success(f"Indexed {result['filename']} ({result['chunks_created']} chunks)")
                    except RuntimeError as exc:
                        st.error(f"{uploaded_file.name}: {exc}")
                progress.progress(index / len(uploaded_files))
            docs = fetch_documents()

    with right:
        st.markdown('<div class="section-label">Indexed documents</div>', unsafe_allow_html=True)
        if not docs:
            st.markdown('<div class="empty-state">No indexed documents yet.</div>', unsafe_allow_html=True)
        for doc in docs:
            filename = escape(str(doc["filename"]))
            created_at = escape(str(doc["created_at"]))
            st.markdown(
                f"""
                <div class="doc-row">
                    <div class="doc-name">{filename}</div>
                    <div class="doc-meta">Indexed {created_at}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Delete document", key=f"docs-delete-{doc['document_id']}", use_container_width=True):
                try:
                    delete_document(doc["document_id"])
                    st.success("Document deleted")
                    st.rerun()
                except RuntimeError as exc:
                    st.error(str(exc))


def render_history_page() -> None:
    render_header()
    sessions = fetch_sessions(limit=100)
    if not sessions:
        st.markdown('<div class="empty-state">No saved chats yet. Start a conversation on the Chat page.</div>', unsafe_allow_html=True)
        return

    for session in sessions:
        title = session_title(session, max_length=80)
        mode = MODE_LABELS.get(session.get("last_mode"), session.get("last_mode") or "No mode")
        meta = f"{session.get('message_count', 0)} messages | Updated {session.get('updated_at')}"
        st.markdown(
            f"""
            <div class="doc-row">
                <div class="doc-name">{escape(title)}</div>
                <div class="doc-meta">{escape(meta)} | {escape(str(mode))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        cols = st.columns([1, 4])
        with cols[0]:
            if st.button("Open", key=f"history-open-{session['session_id']}", use_container_width=True):
                try:
                    load_session_history(session["session_id"])
                    st.session_state.page = "Chat"
                    st.session_state.nav_page = "Chat"
                    st.rerun()
                except RuntimeError as exc:
                    st.error(str(exc))
        with cols[1]:
            st.caption(session["session_id"])


def render_settings_page() -> None:
    render_header()
    render_metrics()
    render_quick_prompts()
    st.divider()
    st.markdown('<div class="section-label">Backend connection</div>', unsafe_allow_html=True)
    api_base_url = st.text_input("FastAPI backend URL", value=st.session_state.api_base_url)
    st.session_state.api_base_url = normalize_base_url(api_base_url)

    cols = st.columns(3)
    with cols[0]:
        if st.button("Check backend", use_container_width=True):
            check_backend()
    with cols[1]:
        if st.button("Refresh documents", use_container_width=True):
            fetch_documents()
    with cols[2]:
        if st.button("Refresh sessions", use_container_width=True):
            fetch_sessions()

    if st.session_state.backend_ok:
        st.markdown('<div class="notice ok">Backend is online</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="notice error">Backend is not reachable</div>', unsafe_allow_html=True)
        if st.session_state.last_error:
            st.caption(st.session_state.last_error)

    st.markdown('<div class="section-label">Current session</div>', unsafe_allow_html=True)
    st.code(st.session_state.session_id or "Not started")


def render_sidebar() -> None:
    with st.sidebar:
        st.header("AI Agent")
        if st.button("New chat", use_container_width=True):
            new_chat()
            st.session_state.page = "Chat"
            st.session_state.nav_page = "Chat"
            st.rerun()

        if st.session_state.backend_ok is None:
            check_backend()

        if st.session_state.backend_ok:
            st.markdown('<div class="notice ok">Backend is online</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="notice error">Backend is not reachable</div>', unsafe_allow_html=True)
            if st.session_state.last_error:
                st.caption(st.session_state.last_error)

        st.divider()
        st.subheader("Recent chats")
        sessions = fetch_sessions(limit=12)
        if not sessions:
            st.caption("No conversations yet")
        for session in sessions:
            active = session["session_id"] == st.session_state.session_id
            title = session_title(session, max_length=28)
            label = f"{'● ' if active else ''}{title}"
            if st.button(label, key=f"sidebar-session-{session['session_id']}", use_container_width=True):
                try:
                    load_session_history(session["session_id"])
                    st.session_state.page = "Chat"
                    st.session_state.nav_page = "Chat"
                    st.rerun()
                except RuntimeError as exc:
                    st.error(str(exc))


def render_metrics() -> None:
    docs_count = len(st.session_state.documents_cache)
    messages_count = len(st.session_state.messages)
    last_mode = next(
        (message.get("mode") for message in reversed(st.session_state.messages) if message["role"] == "assistant"),
        "None",
    )

    last_mode_label = escape(str(MODE_LABELS.get(last_mode, last_mode)))
    cards = [
        ("Indexed documents", str(docs_count), "Available to the RAG tool"),
        ("Messages", str(messages_count), "Current conversation"),
        ("Last mode", last_mode_label, "Most recent agent decision"),
    ]

    cols = st.columns(3)
    for col, (label, value, hint) in zip(cols, cards, strict=True):
        with col:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">{label}</div>
                    <div class="metric-value">{value}</div>
                    <div class="metric-hint">{hint}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def main() -> None:
    st.set_page_config(
        page_title="Multi-Mode AI Agent",
        page_icon=None,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    init_state()
    inject_css()
    render_sidebar()
    render_navbar()
    if st.session_state.page == "Documents":
        render_documents_page()
    elif st.session_state.page == "History":
        render_history_page()
    elif st.session_state.page == "Settings":
        render_settings_page()
    else:
        render_chat_page()


if __name__ == "__main__":
    main()
