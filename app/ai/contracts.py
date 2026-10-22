"""Provider-neutral structured AI contract used by report pipelines."""
from typing import Any, Protocol

class StructuredAIClient(Protocol):
    provider_id: str
    def parse(self, *, model: str, instructions: str, content: list[dict], schema: type[Any], reasoning_effort: str = "none") -> Any: ...
    def test_connection(self) -> None: ...

class ProviderNotEnabledError(RuntimeError):
    pass
