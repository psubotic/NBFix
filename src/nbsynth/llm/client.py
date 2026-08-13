import json

import openai


class LLMClientError(Exception):
    """
    Raised for any failure to get a usable JSON response from the model -
    connection/timeout errors, and responses that aren't valid JSON. Kept
    as a single exception type so callers (the eventual DetectBugsEvent)
    can fail just the LLM check cleanly without needing to know about the
    openai SDK's exception hierarchy.
    """


class LLMClient:
    """
    Thin wrapper around an OpenAI-compatible chat endpoint. Works
    identically against a local Ollama/llama.cpp server or a real hosted
    provider - only base_url/model/api_key change, which is what makes
    comparing a small local model against a large hosted one a
    configuration change rather than a code change.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "not-needed",
        timeout: float = 60.0,
    ) -> None:
        self._client = openai.OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
        self._model = model

    def _create_completion(self, system_prompt: str, user_prompt: str):
        """
        Requests {"type": "json_object"} mode rather than a fuller
        schema-constrained response_format - Ollama's OpenAI-compatible
        endpoint has a known compatibility gap with the json_schema
        wrapper, so schema correctness is enforced downstream (by the
        result-mapping layer) instead of relied on here.
        """
        try:
            return self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )
        except openai.APIConnectionError as exc:
            raise LLMClientError(
                f"Could not reach LLM endpoint for model {self._model!r}: {exc}"
            ) from exc
        except openai.APIError as exc:
            raise LLMClientError(f"LLM request failed: {exc}") from exc

    @staticmethod
    def _parse_content(content) -> dict:
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:
            raise LLMClientError(f"LLM response was not valid JSON: {exc}") from exc

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict:
        """Sends a chat completion request and returns the parsed JSON
        response body as a dict."""
        response = self._create_completion(system_prompt, user_prompt)
        return self._parse_content(response.choices[0].message.content)

    def chat_json_with_usage(self, system_prompt: str, user_prompt: str) -> tuple[dict, dict]:
        """
        Same as chat_json, but also returns token usage - for the
        benchmarking harness's cost/latency comparisons, not needed by
        production callers (DetectBugsEvent uses chat_json).
        """
        response = self._create_completion(system_prompt, user_prompt)
        findings = self._parse_content(response.choices[0].message.content)

        usage = response.usage
        usage_dict = {
            "prompt_tokens": usage.prompt_tokens if usage else None,
            "completion_tokens": usage.completion_tokens if usage else None,
            "total_tokens": usage.total_tokens if usage else None,
        }
        return findings, usage_dict
