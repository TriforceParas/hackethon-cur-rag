from dataclasses import dataclass
from pathlib import Path

from app.utils.file_utils import IMAGE_EXTENSIONS


@dataclass
class LoadedPage:
    text: str
    page_number: int | None = None


class DocumentLoader:
    """Extract text from supported document formats."""

    def load(self, path: Path) -> list[LoadedPage]:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return self._load_pdf(path)
        if suffix == ".docx":
            return self._load_docx(path)
        if suffix in IMAGE_EXTENSIONS:
            return self._load_image_ocr(path)
        if suffix in {
            ".txt",
            ".md",
            ".csv",
            ".json",
            ".xml",
            ".html",
            ".htm",
            ".log",
            ".py",
            ".js",
            ".ts",
            ".java",
            ".c",
            ".cpp",
            ".h",
            ".hpp",
            ".cs",
            ".go",
            ".rs",
            ".php",
            ".rb",
            ".yaml",
            ".yml",
            ".ini",
            ".conf",
        }:
            return [LoadedPage(text=path.read_text(encoding="utf-8", errors="ignore"))]
        raise ValueError(f"Unsupported file type: {suffix}")

    def _load_pdf(self, path: Path) -> list[LoadedPage]:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages: list[LoadedPage] = []
        for index, page in enumerate(reader.pages, start=1):
            pages.append(LoadedPage(text=page.extract_text() or "", page_number=index))
        return pages

    def _load_docx(self, path: Path) -> list[LoadedPage]:
        from docx import Document

        document = Document(str(path))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        return [LoadedPage(text=text)]

    def _load_image_ocr(self, path: Path) -> list[LoadedPage]:
        try:
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Image OCR requires pillow and pytesseract to be installed.") from exc

        try:
            with Image.open(path) as image:
                text = pytesseract.image_to_string(image)
        except pytesseract.TesseractNotFoundError as exc:
            raise RuntimeError(
                "Image OCR requires the Tesseract binary. Install it with your OS package manager."
            ) from exc
        return [LoadedPage(text=text)]
