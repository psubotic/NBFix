import unittest
from unittest.mock import MagicMock, patch

import pytest

# The `llm` extra (openai, httpx) is optional - skip this whole module
# rather than error out collection when it isn't installed, so a plain
# `pip install -e ".[dev]"` (what CI uses) never depends on it.
httpx = pytest.importorskip("httpx")
openai = pytest.importorskip("openai")

from nbfix.llm.client import LLMClient, LLMClientError


def _make_dummy_connection_error():
    request = httpx.Request("POST", "http://localhost:11434/v1/chat/completions")
    return openai.APIConnectionError(request=request)


def _make_completion_response(content: str, usage=None):
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=content))]
    response.usage = usage
    return response


class TestLLMClient(unittest.TestCase):
    @patch("nbfix.llm.client.openai.OpenAI")
    def test_chat_json_returns_parsed_response(self, mock_openai_cls):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create.return_value = _make_completion_response(
            '{"findings": []}'
        )

        client = LLMClient(base_url="http://localhost:11434/v1", model="qwen2.5-coder:14b")
        result = client.chat_json("system prompt", "user prompt")

        self.assertEqual(result, {"findings": []})
        _, kwargs = mock_client.chat.completions.create.call_args
        self.assertEqual(kwargs["model"], "qwen2.5-coder:14b")
        self.assertEqual(kwargs["response_format"], {"type": "json_object"})
        self.assertEqual(
            kwargs["messages"],
            [
                {"role": "system", "content": "system prompt"},
                {"role": "user", "content": "user prompt"},
            ],
        )

    @patch("nbfix.llm.client.openai.OpenAI")
    def test_connection_error_raises_llm_client_error(self, mock_openai_cls):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create.side_effect = _make_dummy_connection_error()

        client = LLMClient(base_url="http://localhost:11434/v1", model="qwen2.5-coder:14b")
        with self.assertRaises(LLMClientError):
            client.chat_json("system prompt", "user prompt")

    @patch("nbfix.llm.client.openai.OpenAI")
    def test_malformed_json_raises_llm_client_error(self, mock_openai_cls):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create.return_value = _make_completion_response(
            "not valid json"
        )

        client = LLMClient(base_url="http://localhost:11434/v1", model="qwen2.5-coder:14b")
        with self.assertRaises(LLMClientError):
            client.chat_json("system prompt", "user prompt")

    @patch("nbfix.llm.client.openai.OpenAI")
    def test_chat_json_with_usage_returns_findings_and_token_counts(self, mock_openai_cls):
        mock_client = mock_openai_cls.return_value
        usage = MagicMock(prompt_tokens=100, completion_tokens=20, total_tokens=120)
        mock_client.chat.completions.create.return_value = _make_completion_response(
            '{"findings": []}', usage=usage
        )

        client = LLMClient(base_url="http://localhost:11434/v1", model="qwen2.5-coder:14b")
        findings, usage_dict = client.chat_json_with_usage("system prompt", "user prompt")

        self.assertEqual(findings, {"findings": []})
        self.assertEqual(
            usage_dict,
            {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        )

    @patch("nbfix.llm.client.openai.OpenAI")
    def test_chat_json_with_usage_handles_missing_usage(self, mock_openai_cls):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create.return_value = _make_completion_response(
            '{"findings": []}', usage=None
        )

        client = LLMClient(base_url="http://localhost:11434/v1", model="qwen2.5-coder:14b")
        _, usage_dict = client.chat_json_with_usage("system prompt", "user prompt")

        self.assertEqual(
            usage_dict,
            {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None},
        )


if __name__ == "__main__":
    unittest.main()
