"""Provider metadata. Untested providers are present but cannot be selected."""
from dataclasses import dataclass

@dataclass(frozen=True)
class ProviderInfo:
    id: str
    label: str
    enabled: bool
    credential_env: str
    credential_service: str

PROVIDERS = {
    "openai": ProviderInfo("openai", "OpenAI", True, "OPENAI_API_KEY", "KeyForMe.OpenAI"),
    "bedrock": ProviderInfo("bedrock", "Amazon Bedrock (not validated)", False, "AWS_BEARER_TOKEN_BEDROCK", "KeyForMe.Bedrock"),
    "anthropic": ProviderInfo("anthropic", "Anthropic (not validated)", False, "ANTHROPIC_API_KEY", "KeyForMe.Anthropic"),
    "gemini": ProviderInfo("gemini", "Google Gemini (not validated)", False, "GEMINI_API_KEY", "KeyForMe.Gemini"),
}

def get_provider_info(provider_id: str) -> ProviderInfo:
    key=str(provider_id or "").strip().lower()
    if key not in PROVIDERS:
        raise ValueError("Unknown AI provider.")
    return PROVIDERS[key]

def enabled_providers():
    return tuple(info for info in PROVIDERS.values() if info.enabled)
