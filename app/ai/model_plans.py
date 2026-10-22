"""Provider-specific model IDs separated from state extraction prompts."""
from dataclasses import dataclass

@dataclass(frozen=True)
class ModelPlan:
    detection: str
    extraction: str
    inventory: str
    recovery: str

OPENAI_MODES = {
    "fast": ModelPlan("gpt-6-luna","gpt-6-luna","gpt-6-luna","gpt-6-luna"),
    "balanced": ModelPlan("gpt-6-luna","gpt-6-luna","gpt-6-luna","gpt-6.1-sol"),
}

def get_model_plan(provider_id="openai", mode="fast"):
    if provider_id != "openai":
        raise ValueError("No validated model plan exists for this provider.")
    if mode not in OPENAI_MODES:
        raise ValueError("Unknown model mode.")
    return OPENAI_MODES[mode]
