import unittest
from unittest.mock import MagicMock, patch

import pytest

# The `llm` extra (openai, httpx) is optional - skip this whole module
# rather than error out collection when it isn't installed, so a plain
# `pip install -e ".[dev]"` (what CI uses) never depends on it.
httpx = pytest.importorskip("httpx")
openai = pytest.importorskip("openai")

from nbsynth.llm.client import LLMClient, LLMClientError


def _make_dummy_connection_error():
    request = httpx.Request("POST", "http://localhost:11434/v1/chat/completions")
    return openai.APIConnectionError(request=request)


def _make_completion_response(content: str):
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=content))]
    return response


class TestLLMClient(unittest.TestCase):
    @patch("nbsynth.llm.client.openai.OpenAI")
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

    @patch("nbsynth.llm.client.openai.OpenAI")
    def test_connection_error_raises_llm_client_error(self, mock_openai_cls):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create.side_effect = _make_dummy_connection_error()

        client = LLMClient(base_url="http://localhost:11434/v1", model="qwen2.5-coder:14b")
        with self.assertRaises(LLMClientError):
            client.chat_json("system prompt", "user prompt")

    @patch("nbsynth.llm.client.openai.OpenAI")
    def test_malformed_json_raises_llm_client_error(self, mock_openai_cls):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create.return_value = _make_completion_response(
            "not valid json"
        )

        client = LLMClient(base_url="http://localhost:11434/v1", model="qwen2.5-coder:14b")
        with self.assertRaises(LLMClientError):
            client.chat_json("system prompt", "user prompt")


if __name__ == "__main__":
    unittest.main()
