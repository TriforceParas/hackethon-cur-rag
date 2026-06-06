from enum import StrEnum


class ChatMode(StrEnum):
    GENERAL_CHAT = "GENERAL_CHAT"
    RAG = "RAG"
    WEB_SEARCH = "WEB_SEARCH"
    MEMORY_CONTEXT = "MEMORY_CONTEXT"
    HYBRID = "HYBRID"
