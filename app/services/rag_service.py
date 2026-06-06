import uuid
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings, get_settings
from app.services.document_loader import LoadedPage
from app.services.llm_service import LLMService
from app.services.memory_service import MemoryService
from app.utils.text_splitter import split_text
from app.vectorstore.faiss_store import FaissVectorStore


@dataclass
class PreparedChunk:
    text: str
    page_number: int | None
    chunk_index: int


class RAGService:
    """Indexes documents and answers questions from retrieved chunks only."""

    def __init__(
        self,
        llm_service: LLMService,
        memory_service: MemoryService,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm_service = llm_service
        self.memory_service = memory_service
        self.vector_store = FaissVectorStore(self.settings.embedding_model, self.settings.vectorstore_dir)

    def prepare_chunks(self, pages: list[LoadedPage]) -> list[PreparedChunk]:
        chunks: list[PreparedChunk] = []
        for page in pages:
            for text in split_text(page.text):
                chunks.append(
                    PreparedChunk(
                        text=text,
                        page_number=page.page_number,
                        chunk_index=len(chunks),
                    )
                )
        return chunks

    def index_document(self, document_id: str, filename: str, pages: list[LoadedPage]) -> int:
        chunks = self.prepare_chunks(pages)
        if not chunks:
            return 0

        chunk_ids = [
            self.memory_service.save_document_chunk(
                document_id=document_id,
                chunk_text=chunk.text,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                vector_id=None,
            )
            for chunk in chunks
        ]
        metadatas = [
            {
                "document_id": document_id,
                "filename": filename,
                "chunk_id": chunk_id,
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number,
                "text": chunk.text,
            }
            for chunk, chunk_id in zip(chunks, chunk_ids, strict=True)
        ]
        vector_ids = self.vector_store.add_texts([chunk.text for chunk in chunks], metadatas)
        for chunk_id, vector_id in zip(chunk_ids, vector_ids, strict=True):
            self.memory_service.update_chunk_vector_id(chunk_id, vector_id)
        return len(chunks)

    def answer(self, question: str, min_score: float | None = None) -> tuple[str, list[dict[str, Any]]]:
        try:
            results = self.vector_store.search(question, top_k=self.settings.top_k)
        except Exception as exc:
            return f"I could not search uploaded documents right now: {exc}", []

        if min_score is not None:
            results = [item for item in results if item.get("score", 0.0) >= min_score]

        if not results:
            return "I could not find this information in the uploaded documents.", []

        context_blocks = []
        for item in results:
            page = f", page {item['page_number']}" if item.get("page_number") else ""
            context_blocks.append(
                f"Source: {item['filename']} (chunk {item['chunk_index']}{page})\n{item['text']}"
            )
        context = "\n\n---\n\n".join(context_blocks)

        prompt = f"""
Use the following document context to answer the user question.
Answer only using the provided context.
If the context does not contain the answer, say: "I could not find this information in the uploaded documents."
Include a concise answer and mention source filenames.

Document context:
{context}

User question:
{question}
"""
        try:
            answer = self.llm_service.generate(prompt)
        except Exception as exc:
            answer = self._build_extractive_fallback(results, exc)

        sources = [
            {
                "filename": item.get("filename"),
                "chunk_id": item.get("chunk_id"),
                "page_number": item.get("page_number"),
                "similarity_score": item.get("score"),
            }
            for item in results
        ]
        return answer, sources

    def _build_extractive_fallback(self, results: list[dict[str, Any]], exc: Exception) -> str:
        excerpts = []
        for item in results[:3]:
            page = f", page {item['page_number']}" if item.get("page_number") else ""
            text = " ".join(str(item.get("text", "")).split())
            if len(text) > 500:
                text = f"{text[:500].rstrip()}..."
            excerpts.append(f"- {item.get('filename')} (chunk {item.get('chunk_index')}{page}): {text}")

        joined_excerpts = "\n".join(excerpts)
        return (
            "I found relevant information in the uploaded documents. Here are the most relevant excerpts:\n"
            f"{joined_excerpts}"
        )

    def delete_document(self, document_id: str) -> None:
        self.vector_store.delete_document(document_id)

    @staticmethod
    def new_document_id() -> str:
        return str(uuid.uuid4())
