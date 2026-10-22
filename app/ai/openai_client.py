"""Compatibility wrapper. New code imports app.ai.runtime.get_ai_client."""
from app.ai.runtime import get_ai_client

def get_openai_client():
    client=get_ai_client()
    if getattr(client,"provider_id",None) != "openai":
        raise RuntimeError("Configured provider is not OpenAI hosted.")
    return client
