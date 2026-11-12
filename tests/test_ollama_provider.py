"""Unit tests for the Ollama connection: what is sent to the local model server."""
import httpx

from src.ai.ollama_provider import OllamaProvider


class _Reply:
    def raise_for_status(self):
        pass

    def json(self):
        return {"message": {"content": " OK "}, "prompt_eval_count": 3, "eval_count": 1}


def _provider(monkeypatch, sent: list) -> OllamaProvider:
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: None)
    monkeypatch.setattr(httpx, "post", lambda url, json, timeout: sent.append(json) or _Reply())
    return OllamaProvider(model="any-model")


def test_thinking_is_switched_off_when_the_caller_asks_for_no_thinking(monkeypatch):
    sent = []

    reply = _provider(monkeypatch, sent).complete(system="s", messages=[{"role": "user", "content": "q"}],
                                                   max_tokens=16, thinking=False)

    assert reply == "OK"
    assert sent[0]["think"] is False


def test_thinking_is_left_to_the_model_when_the_caller_allows_it(monkeypatch):
    sent = []

    _provider(monkeypatch, sent).complete(system="s", messages=[{"role": "user", "content": "q"}], thinking=True)

    assert "think" not in sent[0]


def test_the_token_limit_is_passed_on(monkeypatch):
    sent = []

    _provider(monkeypatch, sent).complete(system="s", messages=[{"role": "user", "content": "q"}], max_tokens=16)

    assert sent[0]["options"]["num_predict"] == 16
