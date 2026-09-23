import json

import httpx
import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import EmbeddingError, LLMUnavailableError
from app.embeddings.openai_compatible import OpenAICompatibleEmbeddingProvider
from app.llm import openai_compatible
from app.llm.base import ChatMessage, LLMProvider, LLMResponse
from app.llm.factory import UnconfiguredLLM, build_llm_provider
from app.llm.openai_compatible import OpenAICompatibleProvider
from app.llm.structured import StructuredOutputError, complete_structured, extract_json_object
from app.llm.usage import track_usage

MESSAGES = [ChatMessage("user", "hi")]


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant(_: float) -> None:
        return None

    monkeypatch.setattr(openai_compatible.asyncio, "sleep", instant)


def provider(handler) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        base_url="https://llm.test/v1",
        api_key="k",
        model="m",
        transport=httpx.MockTransport(handler),
    )


# --- JSON extraction ------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        '{"route": "SQL"}',
        '```json\n{"route": "SQL"}\n```',
        'Sure! Here it is: {"route": "SQL"} Hope that helps.',
        '{"route": "SQL", "reason": "uses {braces} and \\"quotes\\""}',
    ],
)
def test_extract_json_object(text: str) -> None:
    assert extract_json_object(text)["route"] == "SQL"


def test_extract_json_object_rejects_non_json() -> None:
    with pytest.raises(ValueError):
        extract_json_object("no json here")


# --- OpenAI-compatible provider ------------------------------------------------------


async def test_complete_parses_text_usage_and_json_mode() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer k"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "hello"}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            },
        )

    with track_usage() as usage:
        response = await provider(handler).complete(MESSAGES, json_mode=True)
    assert response.text == "hello"
    assert seen["response_format"] == {"type": "json_object"}
    assert usage.total_tokens == 10


async def test_retries_rate_limits_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, json={})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    assert (await provider(handler).complete(MESSAGES)).text == "ok"
    assert calls["n"] == 3


async def test_auth_errors_are_not_retried() -> None:
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={})

    with pytest.raises(LLMUnavailableError, match="credentials"):
        await provider(handler).complete(MESSAGES)
    assert calls["n"] == 1


async def test_stream_yields_deltas_and_records_usage() -> None:
    body = "\n".join(
        [
            'data: {"choices":[{"delta":{"content":"Hel"}}]}',
            "",
            'data: {"choices":[{"delta":{"content":"lo"}}]}',
            'data: {"choices":[],"usage":{"prompt_tokens":5,"completion_tokens":2}}',
            "data: [DONE]",
        ]
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    with track_usage() as usage:
        parts = [delta async for delta in provider(handler).stream(MESSAGES)]
    assert "".join(parts) == "Hello"
    assert usage.total_tokens == 7


async def test_stream_retries_without_stream_options_on_400() -> None:
    payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        payloads.append(payload)
        if "stream_options" in payload:
            return httpx.Response(400, json={"error": "unknown field"})
        return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"x"}}]}\n')

    assert [d async for d in provider(handler).stream(MESSAGES)] == ["x"]
    assert "stream_options" in payloads[0] and "stream_options" not in payloads[1]


async def test_stream_retries_rate_limits_using_retry_after() -> None:
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "2"}, json={})
        return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"ok"}}]}\n')

    assert [d async for d in provider(handler).stream(MESSAGES)] == ["ok"]
    assert calls["n"] == 2
    assert (
        openai_compatible._retry_delay(httpx.Response(429, headers={"retry-after": "99"}), 1)
        == 20.0
    )
    assert openai_compatible._retry_delay(None, 2) == 1.0


async def test_exhausted_quota_reports_the_wait_time() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "1086"}, json={})

    calls = {"n": 0}

    def counting(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return handler(request)

    llm = provider(counting)
    with pytest.raises(LLMUnavailableError, match="about 18 minutes"):
        await llm.complete(MESSAGES)
    assert calls["n"] == 1  # no pointless retries when the quota is gone
    # The circuit breaker makes the next calls fail instantly, without a request.
    with pytest.raises(LLMUnavailableError, match="quota"):
        await llm.complete(MESSAGES)
    with pytest.raises(LLMUnavailableError, match="quota"):
        _ = [d async for d in llm.stream(MESSAGES)]
    assert calls["n"] == 1


async def test_reasoning_effort_is_sent_only_when_configured() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    await provider(handler).complete(MESSAGES)
    await OpenAICompatibleProvider(
        base_url="https://llm.test/v1",
        api_key="k",
        model="m",
        reasoning_effort="low",
        transport=httpx.MockTransport(handler),
    ).complete(MESSAGES)
    assert "reasoning_effort" not in seen[0]
    assert seen[1]["reasoning_effort"] == "low"


# --- structured output -------------------------------------------------------------


class _Answer(BaseModel):
    value: int


class _SequenceLLM(LLMProvider):
    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.calls = 0

    async def complete(self, messages, **_):
        self.calls += 1
        return LLMResponse(self.replies.pop(0))

    async def stream(self, messages, **_):
        yield ""


async def test_structured_output_retries_once_with_error_feedback() -> None:
    llm = _SequenceLLM(['{"value": "not a number"}', '{"value": 3}'])
    assert (await complete_structured(llm, MESSAGES, _Answer)).value == 3
    assert llm.calls == 2


async def test_structured_output_gives_up_after_retries() -> None:
    llm = _SequenceLLM(["nope", "still nope"])
    with pytest.raises(StructuredOutputError):
        await complete_structured(llm, MESSAGES, _Answer)


# --- factory and embeddings ----------------------------------------------------------


async def test_unconfigured_llm_fails_clearly() -> None:
    llm = build_llm_provider(Settings(llm_api_key="", llm_base_url="https://api.openai.com/v1"))
    assert isinstance(llm, UnconfiguredLLM)
    assert not llm.configured
    with pytest.raises(LLMUnavailableError):
        await llm.complete(MESSAGES)


def test_local_ollama_needs_no_api_key() -> None:
    llm = build_llm_provider(
        Settings(
            llm_provider="openai_compatible",
            llm_api_key="",
            llm_base_url="http://localhost:11434/v1",
        )
    )
    assert isinstance(llm, OpenAICompatibleProvider)


async def test_embedding_provider_orders_vectors_and_checks_dimension() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ]
            },
        )

    embedder = OpenAICompatibleEmbeddingProvider(
        base_url="https://e.test/v1",
        api_key="k",
        model="m",
        dimension=2,
        transport=httpx.MockTransport(handler),
    )
    assert await embedder.embed_documents(["a", "b"]) == [[1.0, 0.0], [0.0, 1.0]]
    embedder.dimension = 3
    with pytest.raises(EmbeddingError):
        await embedder.embed_documents(["a", "b"])
