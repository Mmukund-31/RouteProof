from app.core.config import get_settings
from app.services.ai.base import AIProvider
from app.services.ai.claude import ClaudeVisionProvider
from app.services.ai.mock import ManualProvider, MockProvider


def get_provider() -> AIProvider:
    p = get_settings().ai_provider
    if p == "claude":
        return ClaudeVisionProvider()
    if p == "mock":
        return MockProvider()
    return ManualProvider()
