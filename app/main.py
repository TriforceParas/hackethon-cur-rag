from fastapi import FastAPI

from app.api.routes_chat import router as chat_router
from app.api.routes_documents import router as documents_router
from app.api.routes_health import router as health_router
from app.api.routes_sessions import router as sessions_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.sqlite import init_db


configure_logging()
settings = get_settings()

app = FastAPI(title=settings.app_name)


@app.on_event("startup")
async def startup() -> None:
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.vectorstore_dir.mkdir(parents=True, exist_ok=True)
    init_db()


app.include_router(health_router)
app.include_router(chat_router)
app.include_router(documents_router)
app.include_router(sessions_router)

