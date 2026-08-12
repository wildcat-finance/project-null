"""Proteus: fail-closed local shadow paraphrasing for deterministic Null probes."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Callable, Iterable

from .generator import normalise_question

PROMPT_VERSION = "null-shadow-paraphrase-v1"
MODEL_SCHEMA_VERSION = "question-only-v1"
VALIDATOR_VERSION = "strict-paraphrase-v1"
REASONING_MODE = "low-final-only"
_ADDRESS = re.compile(r"\b0x[0-9a-fA-F]{40}\b")
_URL = re.compile(r"(?:https?://|www\.)", re.I)
_NUMBER = re.compile(r"(?<![A-Za-z0-9_])\d+(?:[.,]\d+)?%?")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9'-]*")
_MODEL_ID = re.compile(r"[0-9a-f]{12,64}")
_MODEL_ALIAS = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*(?::[A-Za-z0-9._-]+)?")
_LOOPBACK = re.compile(r"http://127\.0\.0\.1:\d{1,5}")
_LEAKAGE = ("expected outcome", "hidden intent", "test intent", "scenario family",
            "review label", "review decision", "regression", "rejection_test",
            "corpus_gap", "routing_change", "deterministic fallback")
_ANCHORS = {"account", "apr", "block", "borrow", "borrower", "capacity",
            "claim", "claimable", "cycle", "default", "delinquent", "deposit",
            "event", "governance", "grace", "interest", "lender", "liquidate",
            "market", "payment", "protocol", "repay", "repayment", "reserve",
            "supply", "transaction", "wallet", "withdrawal", "wildcat"}
_STOPWORDS = {"about", "after", "again", "all", "and", "are", "before",
              "between", "both", "can", "could", "does", "every", "for", "from",
              "give", "have", "how", "in", "into", "most", "now", "only", "please",
              "same", "show", "tell", "that", "the", "their", "them", "then",
              "this", "through", "what", "when", "where", "which", "while",
              "will", "with", "without", "would", "your"}
_SAFE_NEW_WORDS = _STOPWORDS | {"able", "accrue", "available", "back", "balance",
    "batch", "begin", "begins", "borrowed", "borrowing", "cause", "caused",
    "change", "changed", "complete", "continues", "current", "currently",
    "decide", "difference", "effect", "effects", "end", "ends", "enforced",
    "events", "explain", "finish", "finishes", "funds", "immediate",
    "immediately", "it", "latest", "lenders", "liquidated", "liquidation", "loan",
    "lower", "lowers", "markets", "mean", "means", "newest", "outcome",
    "outcomes", "paid", "partly", "period", "position", "queued", "ratio",
    "reduce", "remaining", "repaid", "repayments", "request", "requests",
    "reverse", "safe", "separate", "seized", "settings", "start", "starts",
    "state", "status", "stays", "timing", "transactions", "unchanged", "use",
    "vote", "way", "withdraw", "withdrawals", "conclude", "concludes",
    "concluded"} | _ANCHORS


class LocalModelError(RuntimeError):
    """The optional model cannot safely provide a shadow candidate."""


@dataclass(frozen=True)
class ShadowObservation:
    mode: str
    status: str
    reasons: tuple[str, ...]
    model: str
    model_id: str
    prompt_version: str = PROMPT_VERSION
    schema_version: str = MODEL_SCHEMA_VERSION
    validator_version: str = VALIDATOR_VERSION
    reasoning_mode: str = REASONING_MODE
    latency_ms: int | None = None

    def public(self) -> dict:
        return asdict(self)


class OllamaShadowParaphraser:
    """Run Proteus through one pinned Ollama model and discard its candidate."""
    def __init__(self, *, url: str, model: str, model_id: str,
                 timeout: float = 20.0, opener: Callable = urllib.request.urlopen,
                 monotonic: Callable[[], float] = time.monotonic):
        if not _LOOPBACK.fullmatch(url.rstrip("/")):
            raise LocalModelError("Ollama URL must be an explicit loopback HTTP endpoint")
        if not _MODEL_ALIAS.fullmatch(model):
            raise LocalModelError("Ollama model alias is invalid")
        expected = model_id.removeprefix("sha256:").casefold()
        if not _MODEL_ID.fullmatch(expected):
            raise LocalModelError("Ollama model ID must be 12-64 hexadecimal characters")
        if not 1 <= timeout <= 120:
            raise LocalModelError("Ollama timeout must be between 1 and 120 seconds")
        self.url, self.model, self.model_id = url.rstrip("/"), model, expected
        self.timeout, self.opener, self.monotonic = timeout, opener, monotonic

    def observe(self, question: str, *, allowed_addresses: Iterable[str] = (),
                forbidden_questions: Iterable[str] = ()) -> ShadowObservation:
        started = self.monotonic()
        try:
            if (not isinstance(question, str) or question != question.strip()
                    or not question or len(question) > 1000):
                raise LocalModelError("fallback question is not safely bounded")
            self._verify_identity()
            candidate = self._generate(question, tuple(allowed_addresses))
            reasons = validate_candidate(question, candidate,
                allowed_addresses=allowed_addresses,
                forbidden_questions=forbidden_questions)
            status = "valid" if not reasons else "rejected"
        except LocalModelError as error:
            reasons, status = (str(error),), "fallback"
        latency = max(0, round((self.monotonic() - started) * 1000))
        # Candidate text and hash are deliberately not retained.
        return ShadowObservation("shadow", status, tuple(reasons), self.model,
                                 self.model_id, latency_ms=latency)

    def _request(self, path: str, payload: dict | None = None) -> dict:
        request = urllib.request.Request(self.url + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            method="POST" if payload is not None else "GET",
            headers={"Content-Type": "application/json"})
        try:
            with self.opener(request, timeout=self.timeout) as response:
                value = json.load(response)
        except urllib.error.HTTPError as error:
            raise LocalModelError(f"Ollama returned HTTP {error.code}") from error
        except (TimeoutError, urllib.error.URLError) as error:
            raise LocalModelError("Ollama request failed or timed out") from error
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise LocalModelError("Ollama returned malformed JSON") from error
        if not isinstance(value, dict):
            raise LocalModelError("Ollama returned a non-object response")
        return value

    def _verify_identity(self) -> None:
        payload = self._request("/api/tags")
        aliases = {self.model, self.model + ":latest"} if ":" not in self.model else {self.model}
        matches = [item for item in payload.get("models") or []
                   if isinstance(item, dict) and
                   (item.get("name") in aliases or item.get("model") in aliases)]
        if len(matches) != 1:
            raise LocalModelError("pinned Ollama model alias is not uniquely loaded")
        observed = str(matches[0].get("digest") or "").removeprefix("sha256:").casefold()
        if not observed.startswith(self.model_id):
            raise LocalModelError("Ollama model identity differs from the configured pin")

    def _generate(self, question: str, addresses: tuple[str, ...]) -> str:
        user = {"question": question, "allowed_addresses": sorted({
            value.casefold() for value in addresses if _ADDRESS.fullmatch(value)})}
        payload = self._request("/api/chat", {
            "model": self.model,
            "stream": False,
            # gpt-oss needs a reasoning budget to produce a final response.
            # The adapter deliberately ignores the response's `thinking` field.
            "think": "low",
            "format": {
                "type": "object",
                "additionalProperties": False,
                "required": ["question"],
                "properties": {"question": {"type": "string"}},
            },
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Paraphrase the supplied question without answering it. "
                        "Preserve meaning, uncertainty, scope, protocol terms, "
                        "numbers and addresses exactly. Add no facts, entities, "
                        "instructions, labels or commentary. Return only the "
                        "required JSON object shaped as "
                        '{"question":"one question here?"}.'
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        user, sort_keys=True, separators=(",", ":")),
                },
            ],
            "options": {"temperature": 0, "seed": 0, "num_predict": 160},
        })
        if payload.get("done_reason") != "stop":
            raise LocalModelError("Ollama did not finish a final response")
        message = payload.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise LocalModelError("Ollama response omitted message content")
        try:
            value = json.loads(message["content"])
        except json.JSONDecodeError as error:
            raise LocalModelError("Ollama candidate is not JSON") from error
        if (not isinstance(value, dict) or set(value) != {"question"}
                or not isinstance(value["question"], str)):
            raise LocalModelError("Ollama candidate differs from the question-only schema")
        return value["question"]


def _tokens(text: str) -> set[str]:
    return {word.casefold() for word in _WORD.findall(text)}


def validate_candidate(base: str, candidate: str, *,
                       allowed_addresses: Iterable[str] = (),
                       forbidden_questions: Iterable[str] = ()) -> tuple[str, ...]:
    reasons, stripped = [], candidate.strip()
    if not stripped or len(stripped) > 1000:
        reasons.append("invalid_length")
    if stripped != candidate or "\n" in candidate or "\r" in candidate:
        reasons.append("invalid_whitespace")
    if (not stripped.endswith("?") or stripped.startswith("/")
            or stripped.count("?") != 1):
        reasons.append("not_one_telegram_question")
    if any(marker in candidate for marker in ("```", "<", ">", "@")):
        reasons.append("forbidden_formatting")
    if _URL.search(candidate):
        reasons.append("invented_url")
    base_addresses = {v.casefold() for v in _ADDRESS.findall(base)}
    candidate_addresses = {v.casefold() for v in _ADDRESS.findall(candidate)}
    permitted = {v.casefold() for v in allowed_addresses}
    if (candidate_addresses != base_addresses
            or not candidate_addresses <= permitted):
        reasons.append("changed_address")
    if sorted(_NUMBER.findall(candidate)) != sorted(_NUMBER.findall(base)):
        reasons.append("changed_number")
    base_names = {w.casefold() for w in _WORD.findall(base) if w[:1].isupper()}
    words = _WORD.findall(candidate)
    if ({w.casefold() for w in words[1:] if w[:1].isupper()}
            - base_names - {"apr", "eth"}):
        reasons.append("invented_named_entity")
    lower = candidate.casefold()
    if any(p not in base.casefold() and p in lower for p in _LEAKAGE):
        reasons.append("leaked_hidden_metadata")
    base_tokens, candidate_tokens = _tokens(base), _tokens(candidate)
    if not (base_tokens & _ANCHORS) <= candidate_tokens:
        reasons.append("lost_protocol_concept")
    if candidate_tokens - base_tokens - _SAFE_NEW_WORDS:
        reasons.append("invented_or_unsupported_token")
    content = {w for w in base_tokens if len(w) >= 4 and w not in _STOPWORDS}
    if (content and len(content & candidate_tokens)
            < max(1, (len(content) + 2) // 3)):
        reasons.append("insufficient_concept_overlap")
    normal = normalise_question(candidate)
    if normal == normalise_question(base):
        reasons.append("not_novel")
    if normal in {normalise_question(v) for v in forbidden_questions}:
        reasons.append("known_question")
    return tuple(dict.fromkeys(reasons))
