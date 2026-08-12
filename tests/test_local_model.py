import io
import json
import pytest
from project_null.local_model import LocalModelError, OllamaShadowParaphraser, validate_candidate

class Response(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *_): self.close()

class Ollama:
    def __init__(self, candidate, digest="a951a23b46a1" + "0" * 52):
        self.candidate, self.digest, self.requests = candidate, digest, []
    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        if request.full_url.endswith("/api/tags"):
            value = {"models": [{"name": "gpt-oss:120b", "digest": self.digest}]}
        else:
            body = json.loads(request.data)
            assert body["stream"] is False and body["think"] == "low"
            assert set(json.loads(body["messages"][1]["content"])) == {
                "allowed_addresses", "question"}
            assert "expected outcome" not in json.dumps(body).casefold()
            value = {"done_reason": "stop", "message": {
                "content": json.dumps({"question": self.candidate}),
                "thinking": "must not be inspected or retained",
            }}
        return Response(json.dumps(value).encode())

def adapter(opener, monotonic=lambda: 1.0):
    return OllamaShadowParaphraser(url="http://127.0.0.1:11435",
        model="gpt-oss:120b", model_id="a951a23b46a1", opener=opener,
        monotonic=monotonic)

def test_valid_candidate_is_observed_but_not_retained():
    transport = Ollama("When does the withdrawal cycle start and when does it finish?")
    times = iter((1.0, 1.125))
    result = adapter(transport, lambda: next(times)).observe(
        "How does the withdrawal cycle begin and end?")
    assert result.status == "valid" and result.latency_ms == 125
    assert set(result.public()) == {"mode", "status", "reasons", "model",
        "model_id", "prompt_version", "schema_version", "validator_version",
        "reasoning_mode", "latency_ms"}
    assert len(transport.requests) == 2

@pytest.mark.parametrize(("candidate", "reason"), (
    ("How does the Coinbase withdrawal cycle begin and end?", "invented_named_entity"),
    ("How does the coinbase withdrawal cycle begin and end?", "invented_or_unsupported_token"),
    ("How does the withdrawal cycle begin? What ends it?", "not_one_telegram_question"),
    ("The expected outcome is refusal; how does the withdrawal cycle end?",
     "leaked_hidden_metadata"),
    ("How does the withdrawal begin and end?", "lost_protocol_concept"),
))
def test_validator_rejects_invention_leakage_and_loss(candidate, reason):
    assert reason in validate_candidate("How does the withdrawal cycle begin and end?", candidate)

def test_validator_requires_exact_addresses_and_numbers():
    market, other = "0x" + "1" * 40, "0x" + "2" * 40
    reasons = validate_candidate(f"Show the latest 5 deposits for market {market}.",
        f"Show the latest 4 deposits for market {other}?", allowed_addresses=(market,))
    assert "changed_address" in reasons and "changed_number" in reasons

def test_identity_mismatch_and_timeout_fail_closed():
    result = adapter(Ollama(
        "When does the withdrawal cycle start and finish?", "b" * 64)).observe(
            "How does the withdrawal cycle begin and end?")
    assert result.status == "fallback" and "identity differs" in result.reasons[0]
    def timeout(*_, **__): raise TimeoutError("private")
    result = adapter(timeout).observe("How does the withdrawal cycle begin and end?")
    assert result.reasons == ("Ollama request failed or timed out",)

def test_unfinished_final_response_falls_back():
    class Unfinished(Ollama):
        def __call__(self, request, timeout):
            response = super().__call__(request, timeout)
            if request.full_url.endswith("/api/chat"):
                value = json.load(response)
                value["done_reason"] = "length"
                return Response(json.dumps(value).encode())
            return response
    result = adapter(Unfinished(
        "When does the withdrawal cycle start and finish?")).observe(
            "How does the withdrawal cycle begin and end?")
    assert result.status == "fallback"
    assert result.reasons == ("Ollama did not finish a final response",)

def test_constructor_rejects_remote_endpoint():
    with pytest.raises(LocalModelError, match="loopback"):
        OllamaShadowParaphraser(url="http://example.com:11434",
            model="gpt-oss:120b", model_id="a951a23b46a1")
