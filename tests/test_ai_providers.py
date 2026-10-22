"""Offline provider-contract tests. No network or real credentials."""
import os, unittest
from types import SimpleNamespace
from unittest.mock import patch, Mock
from pydantic import BaseModel
from app.ai import runtime
from app.ai.contracts import ProviderNotEnabledError
from app.ai.model_plans import get_model_plan
from app.ai.provider_catalog import enabled_providers, get_provider_info
from app.ai.openai_provider import OpenAIHostedClient

class Result(BaseModel):
    value: str

class ProviderTests(unittest.TestCase):
    def tearDown(self): runtime.reset_ai_client()
    def test_only_openai_enabled(self): self.assertEqual([p.id for p in enabled_providers()],["openai"])
    def test_bedrock_disabled_before_credentials(self):
        with self.assertRaises(ProviderNotEnabledError): runtime.configure_ai("bedrock",api_key="not-used")
    def test_anthropic_disabled_before_credentials(self):
        with self.assertRaises(ProviderNotEnabledError): runtime.configure_ai("anthropic",api_key="not-used")
    def test_gemini_disabled_before_credentials(self):
        with self.assertRaises(ProviderNotEnabledError): runtime.configure_ai("gemini",api_key="not-used")
    def test_gemini_has_separate_credential_slot(self):
        info=get_provider_info("gemini")
        self.assertEqual(info.credential_env,"GEMINI_API_KEY")
        self.assertEqual(info.credential_service,"KeyForMe.Gemini")
    def test_missing_openai_key(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(ValueError): runtime.configure_ai("openai")
    def test_openai_adapter_preserves_schema_request(self):
        parsed=Result(value="ok")
        fake=Mock(); fake.responses.parse.return_value=SimpleNamespace(output_parsed=parsed)
        with patch("app.ai.openai_provider.OpenAI",return_value=fake):
            client=OpenAIHostedClient(api_key="synthetic-key")
            result=client.parse(model="synthetic-model",instructions="x",content=[],schema=Result)
        self.assertEqual(result,parsed)
        self.assertIs(fake.responses.parse.call_args.kwargs["text_format"],Result)
    def test_reconfigure_replaces_client(self):
        with patch("app.ai.runtime.OpenAIHostedClient") as cls:
            first=Mock(provider_id="openai"); second=Mock(provider_id="openai")
            cls.side_effect=[first,second]
            runtime.configure_ai("openai",api_key="one")
            runtime.configure_ai("openai",api_key="two")
        self.assertIs(runtime.get_ai_client(),second)
    def test_models_separate_by_role(self):
        plan=get_model_plan("openai","balanced")
        self.assertEqual(plan.extraction,"gpt-6-luna")
        self.assertEqual(plan.recovery,"gpt-6.1-sol")
    def test_unknown_provider(self):
        with self.assertRaises(ValueError): get_provider_info("unknown")

if __name__=="__main__": unittest.main()
