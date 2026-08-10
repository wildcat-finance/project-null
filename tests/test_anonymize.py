from project_null.anonymize import Anonymizer
from project_null.generator import Generator
from project_null.schema import (
    Delivery, Feedback, OutcomeKind, ReviewDecision, raw_expiry, stable_id,
)
from project_null.store import Store

START = "2026-08-11T00:00:00Z"


def test_anonymization_breaks_telegram_link_and_scrubs_storage(tmp_path):
    path = tmp_path / "null.db"
    store = Store(str(path))
    generated = Generator(clock=lambda: START).generate(seed=4)
    probe = generated.probe
    # Use a reviewed human-authored-looking string containing every direct
    # identifier class the long-term boundary must remove.
    object.__setattr__(probe, "text", (
        "Ask @some_user about 0x1111111111111111111111111111111111111111 "
        "at https://t.me/example and ticket 987654321."))
    store.append_many([generated.scenario, probe])
    delivery = Delivery(
        delivery_id=stable_id("delivery", {"unique": 987654321}),
        probe_id=probe.probe_id, chat_id=-100987654321, message_id=987654321,
        thread_id=None, delivered_at=START, raw_expires_at=raw_expiry(START))
    store.append(delivery)
    reviewed_at = "2026-08-11T00:00:01Z"
    feedback = Feedback(
        feedback_id=stable_id("feedback", {"unique": 987654321}),
        probe_id=probe.probe_id, reviewer_user_id=987654321,
        decision=ReviewDecision.CORPUS_GAP,
        expected_outcome=OutcomeKind.ANSWERED,
        note="Docs gap reported by @some_user at https://t.me/example",
        created_at=reviewed_at, raw_expires_at=raw_expiry(reviewed_at))
    store.append(feedback)
    store.set_control(f"delivery:{probe.probe_id}", "sent")

    first = Anonymizer(store).run("2026-09-10T00:00:00Z")
    assert first.anonymized == first.candidates == 1
    question = store.list("anonymized_question")[0]
    assert question["text"] == (
        "Ask [username] about [address] at [url] and ticket [identifier].")
    assert "probe_id" not in question and "chat_id" not in question
    # One second later the feedback reaches its own, non-sliding deadline.
    Anonymizer(store).run("2026-09-10T00:00:01Z")
    assert store.list("probe") == store.list("delivery") == store.list("feedback") == []
    assert store.control(f"delivery:{probe.probe_id}") is None
    store.close()
    raw = path.read_bytes()
    assert b"-100987654321" not in raw
    assert b"@some_user" not in raw


def test_unreviewed_and_discarded_questions_do_not_survive(tmp_path):
    store = Store(str(tmp_path / "null.db"))
    first = Generator(clock=lambda: START).generate(seed=10)
    second = Generator(clock=lambda: START).generate(seed=11)
    store.append_many([first.scenario, first.probe, second.scenario, second.probe])
    feedback = Feedback(
        feedback_id=stable_id("feedback", {"discard": 1}),
        probe_id=second.probe.probe_id, reviewer_user_id=7,
        decision=ReviewDecision.DISCARD,
        expected_outcome=OutcomeKind.REFUSED, note="Not useful",
        created_at=START, raw_expires_at=raw_expiry(START))
    store.append(feedback)
    Anonymizer(store).run("2026-09-10T00:00:00Z")
    assert store.list("anonymized_question") == []
    assert store.list("export_candidate") == []
