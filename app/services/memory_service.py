import uuid
from pathlib import Path
from typing import Any

from app.db.sqlite import get_connection, init_db


class MemoryService:
    """SQLite-backed conversation, session, and document metadata storage."""

    def __init__(self) -> None:
        init_db()

    def ensure_session(self, session_id: str | None = None) -> str:
        sid = session_id or str(uuid.uuid4())
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id) VALUES (?)
                ON CONFLICT(id) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                """,
                (sid,),
            )
        return sid

    def save_message(self, session_id: str, role: str, content: str, mode: str | None = None) -> str:
        message_id = str(uuid.uuid4())
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO messages (id, session_id, role, content, mode)
                VALUES (?, ?, ?, ?, ?)
                """,
                (message_id, session_id, role, content, mode),
            )
            conn.execute("UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (session_id,))
        return message_id

    def get_last_messages(self, session_id: str, limit: int = 10) -> list[dict[str, Any]]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT role, content, mode, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def get_session_history(self, session_id: str) -> list[dict[str, Any]]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT role, content, mode, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    s.id AS session_id,
                    s.created_at,
                    s.updated_at,
                    COUNT(m.id) AS message_count,
                    COALESCE(
                        (
                            SELECT content
                            FROM messages
                            WHERE session_id = s.id AND role = 'user'
                            ORDER BY created_at ASC
                            LIMIT 1
                        ),
                        'New conversation'
                    ) AS title,
                    (
                        SELECT mode
                        FROM messages
                        WHERE session_id = s.id AND role = 'assistant'
                        ORDER BY created_at DESC
                        LIMIT 1
                    ) AS last_mode
                FROM sessions s
                LEFT JOIN messages m ON m.session_id = s.id
                GROUP BY s.id
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_document(self, document_id: str, filename: str, path: Path) -> None:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO documents (id, filename, path) VALUES (?, ?, ?)",
                (document_id, filename, str(path)),
            )

    def list_documents(self) -> list[dict[str, Any]]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id AS document_id, filename, created_at
                FROM documents
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def has_documents(self) -> bool:
        with get_connection() as conn:
            row = conn.execute("SELECT 1 FROM documents LIMIT 1").fetchone()
        return row is not None

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id, filename, path, created_at FROM documents WHERE id = ?",
                (document_id,),
            ).fetchone()
        return dict(row) if row else None

    def delete_document(self, document_id: str) -> None:
        with get_connection() as conn:
            conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))

    def save_document_chunk(
        self,
        document_id: str,
        chunk_text: str,
        chunk_index: int,
        page_number: int | None,
        vector_id: str | None,
    ) -> str:
        chunk_id = str(uuid.uuid4())
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO document_chunks
                    (id, document_id, chunk_text, chunk_index, page_number, vector_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (chunk_id, document_id, chunk_text, chunk_index, page_number, vector_id),
            )
        return chunk_id

    def update_chunk_vector_id(self, chunk_id: str, vector_id: str) -> None:
        with get_connection() as conn:
            conn.execute("UPDATE document_chunks SET vector_id = ? WHERE id = ?", (vector_id, chunk_id))
