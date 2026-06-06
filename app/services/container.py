from app.core.config import get_settings
from app.services.llm_service import LLMService
from app.services.agent_service import AgentService
from app.services.memory_service import MemoryService
from app.services.rag_service import RAGService
from app.services.router_service import RouterService
from app.services.web_search_service import WebSearchService


settings = get_settings()
memory_service = MemoryService()
llm_service = LLMService(settings)
router_service = RouterService(llm_service)
rag_service = RAGService(llm_service, memory_service, settings)
web_search_service = WebSearchService(llm_service, settings)
agent_service = AgentService(
    llm_service=llm_service,
    memory_service=memory_service,
    router_service=router_service,
    rag_service=rag_service,
    web_search_service=web_search_service,
    settings=settings,
)
