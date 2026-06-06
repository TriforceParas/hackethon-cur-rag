from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.config import get_settings
from app.schemas.documents import DocumentDeleteResponse, DocumentListItem, DocumentUploadResponse
from app.services.container import memory_service, rag_service
from app.services.document_loader import DocumentLoader
from app.utils.file_utils import is_allowed_file, safe_filename


router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...)) -> DocumentUploadResponse:
    if not file.filename or not is_allowed_file(file.filename):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Upload PDF, DOCX, images, or common text/code files.",
        )

    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    document_id = rag_service.new_document_id()
    filename = safe_filename(file.filename)
    stored_path = settings.upload_dir / f"{document_id}_{filename}"
    stored_path.write_bytes(await file.read())

    try:
        pages = DocumentLoader().load(stored_path)
        if not any(page.text.strip() for page in pages):
            stored_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="Document did not contain extractable text.")

        memory_service.save_document(document_id, filename, stored_path)
        chunks_created = rag_service.index_document(document_id, filename, pages)
        if chunks_created == 0:
            memory_service.delete_document(document_id)
            stored_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="Document did not contain enough text to index.")
    except HTTPException:
        raise
    except Exception as exc:
        memory_service.delete_document(document_id)
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Could not index document: {exc}") from exc

    return DocumentUploadResponse(
        document_id=document_id,
        filename=filename,
        chunks_created=chunks_created,
        status="indexed",
    )


@router.get("", response_model=list[DocumentListItem])
async def list_documents() -> list[DocumentListItem]:
    return [DocumentListItem(**item) for item in memory_service.list_documents()]


@router.delete("/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(document_id: str) -> DocumentDeleteResponse:
    document = memory_service.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        rag_service.delete_document(document_id)
    except Exception:
        pass
    memory_service.delete_document(document_id)
    Path(document["path"]).unlink(missing_ok=True)
    return DocumentDeleteResponse(document_id=document_id, status="deleted")
