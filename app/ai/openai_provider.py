"""OpenAI-hosted implementation of the structured AI contract."""
from openai import OpenAI

class OpenAIHostedClient:
    provider_id = "openai"
    def __init__(self, *, api_key: str):
        key=str(api_key or "").strip()
        if not key or any(c.isspace() for c in key):
            raise ValueError("A nonempty OpenAI API key without whitespace is required.")
        self._client=OpenAI(api_key=key)
    def parse(self, *, model, instructions, content, schema, reasoning_effort="none"):
        response=self._client.responses.parse(
            model=model,
            reasoning={"effort": reasoning_effort},
            input=[{"role":"system","content":instructions},{"role":"user","content":content}],
            text_format=schema,
        )
        if response.output_parsed is None:
            raise RuntimeError("AI provider returned no structured result.")
        return response.output_parsed
    def test_connection(self):
        self._client.models.list()
