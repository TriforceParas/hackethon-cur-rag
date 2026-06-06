from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    chunks_created: int
    status: str


class DocumentListItem(BaseModel):
    document_id: str
    filename: str
    created_at: str


class DocumentDeleteResponse(BaseModel):
    document_id: str
    status: str

