"""One configured AI client per process. Provider changes require reconfiguration."""
import os
from app.ai.contracts import ProviderNotEnabledError
from app.ai.provider_catalog import get_provider_info
from app.ai.openai_provider import OpenAIHostedClient

_client=None
_configured_provider=None

def configure_ai(provider_id="openai", *, api_key=None, test_connection=False):
    global _client, _configured_provider
    info=get_provider_info(provider_id)
    if not info.enabled:
        raise ProviderNotEnabledError(f"{info.label} is not enabled in this build.")
    key=(api_key if api_key is not None else os.getenv(info.credential_env, "")).strip()
    if info.id == "openai":
        candidate=OpenAIHostedClient(api_key=key)
    else:
        raise ProviderNotEnabledError(f"{info.label} has no validated adapter in this build.")
    if test_connection:
        candidate.test_connection()
    _client=candidate
    _configured_provider=info.id
    return candidate

def get_ai_client():
    if _client is None:
        raise RuntimeError("AI client is not configured.")
    return _client

def configured_provider():
    return _configured_provider

def reset_ai_client():
    global _client, _configured_provider
    _client=None; _configured_provider=None
