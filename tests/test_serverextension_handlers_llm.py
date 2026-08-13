import json
from unittest.mock import MagicMock, patch

import pytest
from tornado.httpclient import HTTPClientError

pytest.importorskip("openai")
httpx = pytest.importorskip("httpx")

TEST_NOTEBOOK = [
    {"cell_type": "code", "source": "x = 1"},
    {"cell_type": "code", "source": "y = x + 1"},
]


async def _post_event(jp_fetch, event, notebook_id, params=None):
    try:
        response = await jp_fetch(
            "nbfix",
            "api",
            "event",
            method="POST",
            body=json.dumps(
                {"event": event, "notebook_id": notebook_id, "params": params or {}}
            ),
        )
    except HTTPClientError as exc:
        return exc.response.code, json.loads(exc.response.body)
    return response.code, json.loads(response.body)


async def test_detect_bugs_without_open_session_returns_404(jp_fetch):
    code, payload = await _post_event(
        jp_fetch, "detect_bugs", "never-opened.ipynb", {"scope": "full"}
    )
    assert code == 404
    assert payload["status"] == "error"


async def test_detect_bugs_invalid_scope_returns_400(jp_fetch):
    notebook_id = "nb1.ipynb"
    await _post_event(
        jp_fetch, "open_notebook", notebook_id, {"notebook_json": TEST_NOTEBOOK}
    )
    code, payload = await _post_event(
        jp_fetch, "detect_bugs", notebook_id, {"scope": "not_a_scope"}
    )
    assert code == 400
    assert payload["status"] == "error"


async def test_detect_bugs_cell_scope_without_cell_index_returns_400(jp_fetch):
    notebook_id = "nb2.ipynb"
    await _post_event(
        jp_fetch, "open_notebook", notebook_id, {"notebook_json": TEST_NOTEBOOK}
    )
    code, payload = await _post_event(
        jp_fetch, "detect_bugs", notebook_id, {"scope": "cell"}
    )
    assert code == 400
    assert payload["status"] == "error"


def _mock_openai_response(content: str):
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=content))]
    return response


@patch("nbfix.llm.client.openai.OpenAI")
async def test_detect_bugs_happy_path(mock_openai_cls, jp_fetch):
    mock_client = mock_openai_cls.return_value
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        '{"findings": []}'
    )

    notebook_id = "nb3.ipynb"
    await _post_event(
        jp_fetch, "open_notebook", notebook_id, {"notebook_json": TEST_NOTEBOOK}
    )
    code, payload = await _post_event(
        jp_fetch, "detect_bugs", notebook_id, {"scope": "full"}
    )
    assert code == 200
    assert payload["status"] == "success"
    assert payload["diagnostics"] == []


@patch("nbfix.llm.client.openai.OpenAI")
async def test_detect_bugs_unreachable_endpoint_returns_500_not_crash(
    mock_openai_cls, jp_fetch
):
    import openai

    request = httpx.Request("POST", "http://localhost:11434/v1/chat/completions")
    mock_client = mock_openai_cls.return_value
    mock_client.chat.completions.create.side_effect = openai.APIConnectionError(
        request=request
    )

    notebook_id = "nb4.ipynb"
    await _post_event(
        jp_fetch, "open_notebook", notebook_id, {"notebook_json": TEST_NOTEBOOK}
    )
    code, payload = await _post_event(
        jp_fetch, "detect_bugs", notebook_id, {"scope": "full"}
    )
    assert code == 500
    assert payload["status"] == "error"
