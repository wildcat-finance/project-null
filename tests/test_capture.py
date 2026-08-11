from project_null.capture import OutcomeCapture, classify
from project_null.generator import Generator
from project_null.schema import Delivery, OutcomeKind, raw_expiry, stable_id
from project_null.store import Store

NOW = "2026-08-11T00:00:00Z"


def prepared(store):
    item = Generator(clock=lambda: NOW).generate(seed=1)
    store.append_many([item.scenario, item.probe])
    delivery = Delivery(
        delivery_id=stable_id("delivery", {"x": 1}),
        probe_id=item.probe.probe_id, chat_id=-100, message_id=50,
        thread_id=None, delivered_at=NOW, raw_expires_at=raw_expiry(NOW))
    store.append(delivery)
    return item.probe.probe_id


def test_public_shapes_classify_without_answer_content_storage(tmp_path):
    store = Store(str(tmp_path / "null.db"))
    probe_id = prepared(store)
    capture = OutcomeCapture(store)
    text = ("Explanation\n\nWithdrawal cycles begin on request.\n\nSources\n\n"
            "https://github.com/wildcat-finance/wildcat-docs/blob/abc/page.md")
    outcome = capture.observe(
        probe_id=probe_id, reply_message_id=60, text=text,
        observed_at="2026-08-11T00:00:02Z")
    payload = store.get(outcome.outcome_id)
    assert payload["outcome"] == "answered"
    assert payload["route"] == "corpus"
    assert payload["latency_ms"] == 2000
    assert "Withdrawal cycles" not in str(payload)
    assert len(payload["citation_urls"]) == 1


def test_refusal_point_and_unknown_shapes():
    assert classify("The appropriate destination is support.")[0] is OutcomeKind.POINTED
    assert classify("I can't comply with that.")[0] is OutcomeKind.REFUSED
    assert classify("totally novel output")[0] is OutcomeKind.FAILED


def test_rate_limit_is_a_harness_failure_not_an_answer_shape():
    outcome, route, error = classify(
        "Aleph is rate-limited for this chat and user. Please wait before asking again.")
    assert outcome is OutcomeKind.FAILED
    assert route == "rate_limited"
    assert error == "rate_limited"


def test_transaction_history_heading_is_a_live_answer_shape():
    text = (
        "Transaction history\n\n"
        "Latest 1 matching event(s) for Example Market (limit 1; withdrawal "
        "request):\n"
        "- Withdrawal request: 1 USDC; 2026-08-11T00:00:00+00:00; "
        "block 1; transaction 0x" + "1" * 64 + "\n\n"
        "Observed at Ethereum block 1 via Wildcat Data Gateway release v2.0.30.")
    outcome, route, error = classify(text)
    assert outcome is OutcomeKind.ANSWERED
    assert route == "live"
    assert error is None


def test_transaction_history_words_without_the_heading_remain_unrecognized():
    outcome, route, error = classify(
        "This arbitrary sentence mentions transaction history but has no "
        "reviewed response shape.")
    assert outcome is OutcomeKind.FAILED
    assert route == "unrecognized"
    assert error == "unrecognized_format"


def test_silence_becomes_failed_once(tmp_path):
    store = Store(str(tmp_path / "null.db"))
    prepared(store)
    capture = OutcomeCapture(store)
    assert capture.mark_timeouts(now="2026-08-11T00:02:00Z") == 1
    assert capture.mark_timeouts(now="2026-08-11T00:03:00Z") == 0
    outcome = store.list("aleph_outcome")[0]
    assert outcome["outcome"] == "failed" and outcome["error_kind"] == "timeout"
