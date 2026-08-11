import json
import re

import pytest

from project_null.generator import Generator
from project_null.store import Store
from project_null.telegram import (
    TelegramHTTP, TelegramShell, TelegramTimeout,
)

NOW = "2026-08-11T00:00:00Z"


class FakeAPI:
    def __init__(self, updates=()):
        self.updates = list(updates)
        self.calls = []
        self.next_message = 100
        self.poll_timeout = False
        self.send_timeout = False

    def call(self, method, payload=None):
        self.calls.append((method, payload or {}))
        if method == "getMe":
            return {"id": 9, "username": "ProjectNull_bot",
                    "can_read_all_group_messages": False}
        if method == "getWebhookInfo":
            return {"url": ""}
        if method == "getUpdates":
            if self.poll_timeout:
                raise TelegramTimeout("fixture poll timed out")
            offset = payload["offset"]
            return [item for item in self.updates if item["update_id"] >= offset]
        if method == "sendMessage":
            if self.send_timeout:
                raise TelegramTimeout("fixture send timed out")
            self.next_message += 1
            return {"message_id": self.next_message}
        raise AssertionError(method)


def update(update_id, text, *, user=7, bot=False, chat=-100):
    return {"update_id": update_id, "message": {
        "message_id": update_id + 10, "text": text,
        "chat": {"id": chat, "type": "supergroup"},
        "from": {"id": user, "is_bot": bot},
    }}


def bot_reply(update_id, text, reply_to):
    item = update(update_id, text, user=8728174629, bot=True)
    item["message"]["from"]["username"] = "ProjectAlephWildcat_bot"
    item["message"]["reply_to_message"] = {"message_id": reply_to}
    return item


def shell(tmp_path, api, clock=lambda: NOW):
    store = Store(str(tmp_path / "null.db"))
    instance = TelegramShell(
        store, Generator(clock=lambda: NOW), api,
        aleph_username="ProjectAlephWildcat_bot",
        aleph_bot_id=8728174629,
        allowed_chat_ids={-100}, operator_user_ids={7}, clock=clock)
    instance.startup()
    return instance, store


def test_probe_is_addressed_to_aleph_and_checkpointed(tmp_path):
    api = FakeAPI([update(1, "/probe@ProjectNull_bot")])
    instance, store = shell(tmp_path, api)
    assert instance.poll_once() == 1
    probe_sends = [payload for method, payload in api.calls
                   if method == "sendMessage" and payload["text"].startswith("/ask@")]
    assert len(probe_sends) == 1
    assert probe_sends[0]["text"].startswith("/ask@ProjectAlephWildcat_bot ")
    assert len(store.list("probe")) == len(store.list("delivery")) == 1
    assert store.checkpoint("telegram") == 2


def test_restart_does_not_resend_a_prepared_probe(tmp_path):
    duplicate = update(4, "/probe@ProjectNull_bot")
    api = FakeAPI([duplicate, duplicate])
    instance, store = shell(tmp_path, api)
    instance.poll_once()
    probe_sends = [payload for method, payload in api.calls
                   if method == "sendMessage" and payload["text"].startswith("/ask@")]
    assert len(probe_sends) == 1


def test_long_poll_timeout_is_an_empty_uncheckpointed_iteration(tmp_path):
    api = FakeAPI()
    instance, store = shell(tmp_path, api)
    api.poll_timeout = True

    assert instance.poll_once() == 0
    assert store.checkpoint("telegram") == 0
    assert store.list("probe") == []


def test_send_timeout_keeps_probe_uncertain_and_confirms_command(tmp_path):
    api = FakeAPI([update(1, "/probe@ProjectNull_bot")])
    instance, store = shell(tmp_path, api)
    api.send_timeout = True

    assert instance.poll_once() == 1
    probe = store.list("probe")[0]
    assert store.control(f"delivery:{probe['probe_id']}") == "uncertain"
    assert store.list("delivery") == []
    assert store.checkpoint("telegram") == 2


def test_http_read_timeout_is_typed_without_transport_detail(monkeypatch):
    def timed_out(*_args, **_kwargs):
        raise TimeoutError("The read operation timed out")

    monkeypatch.setattr("urllib.request.urlopen", timed_out)
    with pytest.raises(TelegramTimeout, match="Telegram getUpdates timed out"):
        TelegramHTTP("fixture-token").call("getUpdates")


def test_pause_mode_burst_and_loop_prevention(tmp_path):
    api = FakeAPI([
        update(1, "/mode@ProjectNull_bot false_premise"),
        update(2, "/pause@ProjectNull_bot"),
        update(3, "/burst@ProjectNull_bot 2"),
        update(4, "/resume@ProjectNull_bot"),
        update(5, "/burst@ProjectNull_bot 2"),
        update(6, "/probe@ProjectNull_bot", user=99),
        update(7, "/probe@ProjectNull_bot", user=8728174629, bot=True),
    ])
    instance, store = shell(tmp_path, api)
    instance.poll_once()
    assert len(store.list("probe")) == 2
    assert all(item["scenario_id"] for item in store.list("probe"))
    assert store.control("mode") == "false_premise"
    assert store.control("paused") == "false"


def test_commands_for_other_bots_and_ambient_text_are_ignored(tmp_path):
    api = FakeAPI([
        update(1, "/probe@SomeoneElse_bot"),
        update(2, "please make a probe"), update(3, "/probe"),
    ])
    instance, store = shell(tmp_path, api)
    instance.poll_once()
    assert store.list("probe") == []


def test_aleph_reply_and_human_feedback_are_correlated(tmp_path):
    api = FakeAPI([update(1, "/probe@ProjectNull_bot")])
    instance, store = shell(tmp_path, api)
    instance.poll_once()
    delivery = store.list("delivery")[0]
    api.updates = [bot_reply(
        2, "I can't produce a supported answer right now.",
        delivery["message_id"])]
    instance.poll_once()
    outcome = store.list("aleph_outcome")[0]
    assert outcome["outcome"] == "abstained"
    feedback = update(
        3, "/feedback@ProjectNull_bot corpus_gap answered missing documentation")
    feedback["message"]["reply_to_message"] = {"message_id": 12}
    api.updates = [feedback]
    instance.poll_once()
    saved = store.list("feedback")[0]
    assert saved["probe_id"] == delivery["probe_id"]
    assert saved["decision"] == "corpus_gap"
    assert saved["expected_outcome"] == "answered"
    finalize = update(4, "/finalize@ProjectNull_bot")
    finalize["message"]["reply_to_message"] = {"message_id": 12}
    api.updates = [finalize]
    instance.poll_once()
    assert store.list("probe") == store.list("delivery") == []
    assert store.list("aleph_outcome") == store.list("feedback") == []
    assert len(store.list("anonymized_question")) == 1
    assert store.list("export_candidate")[0]["kind"] == "corpus_proposal"
    evidence = json.loads(store.control("peer_reply_evidence"))
    assert evidence == {"count": 1, "last_observed_at": NOW}


def test_review_queue_codes_finalize_without_historical_reply(tmp_path):
    api = FakeAPI([update(1, "/probe@ProjectNull_bot")])
    instance, store = shell(tmp_path, api)
    instance.poll_once()
    delivery = store.list("delivery")[0]
    api.updates = [bot_reply(
        2, "I can't produce a supported answer right now.",
        delivery["message_id"])]
    instance.poll_once()

    api.updates = [update(3, "/queue@ProjectNull_bot")]
    instance.poll_once()
    queue = [payload["text"] for method, payload in api.calls
             if method == "sendMessage"][-1]
    code = re.search(r"^([0-9a-f]{12}) family=", queue, re.M).group(1)
    assert "expected=answered" in queue
    assert "observed=abstained" in queue
    assert "state=feedback" in queue
    assert delivery["probe_id"] not in queue
    assert str(delivery["chat_id"]) not in queue

    api.updates = [update(
        4, f"/feedback@ProjectNull_bot {code} regression answered "
           "captured without an old reply")]
    instance.poll_once()
    feedback = store.list("feedback")[0]
    assert feedback["probe_id"] == delivery["probe_id"]
    assert feedback["decision"] == "regression"
    assert feedback["note"] == "captured without an old reply"

    api.updates = [update(5, f"/finalize@ProjectNull_bot {code}")]
    instance.poll_once()
    assert store.list("probe") == store.list("delivery") == []
    assert store.list("aleph_outcome") == store.list("feedback") == []
    assert len(store.list("export_candidate")) == 1


def test_unknown_review_code_fails_closed(tmp_path):
    api = FakeAPI([update(
        1, "/feedback@ProjectNull_bot 000000000000 regression answered note")])
    instance, store = shell(tmp_path, api)
    instance.poll_once()

    error = [payload["text"] for method, payload in api.calls
             if method == "sendMessage"][-1]
    assert error == "review code is unknown or already finalized"
    assert store.list("feedback") == []


def test_brace_review_batches_return_ordered_one_to_one_receipts(tmp_path):
    api = FakeAPI([update(1, "/burst@ProjectNull_bot 3")])
    instance, store = shell(tmp_path, api)
    instance.poll_once()
    codes = [instance._review_code(item["probe_id"])
             for item in store.list("probe")]

    api.updates = [update(
        2,
        "/feedback@ProjectNull_bot {\n"
        f"{codes[0]} regression answered first result\n"
        f"{codes[1]} routing_change refused second result\n"
        f"{codes[2]} rejection_test refused third result\n"
        "}")]
    instance.poll_once()
    feedback_receipt = [payload["text"] for method, payload in api.calls
                        if method == "sendMessage"][-1]
    assert feedback_receipt.splitlines() == [
        "Feedback batch results:",
        f"1. {codes[0]} — Recorded regression; expected=answered.",
        f"2. {codes[1]} — Recorded routing_change; expected=refused.",
        f"3. {codes[2]} — Recorded rejection_test; expected=refused.",
    ]
    assert {item["note"] for item in store.list("feedback")} == {
        "first result", "second result", "third result"}

    api.updates = [update(
        3,
        "/finalize@ProjectNull_bot {\n" + "\n".join(codes) + "\n}")]
    instance.poll_once()
    finalize_receipt = [payload["text"] for method, payload in api.calls
                        if method == "sendMessage"][-1]
    lines = finalize_receipt.splitlines()
    assert lines[0] == "Finalize batch results:"
    assert [line.split(" — ", 1)[0] for line in lines[1:]] == [
        f"1. {codes[0]}", f"2. {codes[1]}", f"3. {codes[2]}"]
    assert all("Finalized; candidates=1" in line for line in lines[1:])
    assert store.list("probe") == store.list("feedback") == []
    assert len(store.list("export_candidate")) == 3


def test_feedback_batch_isolates_unknown_and_duplicate_codes(tmp_path):
    api = FakeAPI([update(1, "/burst@ProjectNull_bot 2")])
    instance, store = shell(tmp_path, api)
    instance.poll_once()
    codes = [instance._review_code(item["probe_id"])
             for item in store.list("probe")]

    api.updates = [update(
        2,
        "/feedback@ProjectNull_bot {\n"
        f"{codes[0]} regression answered valid first\n"
        "000000000000 regression answered unknown\n"
        f"{codes[0]} regression answered duplicate\n"
        f"{codes[1]} routing_change answered valid second\n"
        "}")]
    instance.poll_once()

    receipt = [payload["text"] for method, payload in api.calls
               if method == "sendMessage"][-1]
    lines = receipt.splitlines()
    assert len(lines) == 5
    assert f"1. {codes[0]} — Recorded regression" in lines[1]
    assert "2. 000000000000 — Error: review code is unknown" in lines[2]
    assert f"3. {codes[0]} — Error: duplicate review code in batch" == lines[3]
    assert f"4. {codes[1]} — Recorded routing_change" in lines[4]
    assert len(store.list("feedback")) == 2

    api.updates = [update(
        3,
        "/finalize@ProjectNull_bot {\n"
        f"{codes[0]}\n"
        "000000000000\n"
        f"{codes[1]} unexpected text\n"
        f"{codes[1]}\n"
        "}")]
    instance.poll_once()
    receipt = [payload["text"] for method, payload in api.calls
               if method == "sendMessage"][-1]
    lines = receipt.splitlines()
    assert f"1. {codes[0]} — Finalized; candidates=1" in lines[1]
    assert "2. 000000000000 — Error: review code is unknown" in lines[2]
    assert (f"3. {codes[1]} — Error: finalize batch entries must contain one "
            "review code") == lines[3]
    assert f"4. {codes[1]} — Finalized; candidates=1" in lines[4]
    assert store.list("probe") == store.list("feedback") == []


def test_review_batch_syntax_and_size_fail_closed(tmp_path):
    oversized = "\n".join(
        f"{index:012x} regression answered note" for index in range(21))
    api = FakeAPI([update(
        1, "/feedback@ProjectNull_bot {\n" + oversized + "\n}")])
    instance, store = shell(tmp_path, api)
    instance.poll_once()
    error = [payload["text"] for method, payload in api.calls
             if method == "sendMessage"][-1]
    assert error == "review batch must contain at most 20 entries"
    assert store.list("feedback") == []

    api.updates = [update(
        2, "/feedback@ProjectNull_bot {\n000000000000 regression answered")]
    instance.poll_once()
    error = [payload["text"] for method, payload in api.calls
             if method == "sendMessage"][-1]
    assert error == "review batch must end with }"


def test_aleph_latency_uses_the_same_local_clock_as_delivery(tmp_path):
    times = iter([
        "2026-08-11T00:00:00.750000Z",
        "2026-08-11T00:00:01.250000Z",
    ])
    api = FakeAPI([update(1, "/probe@ProjectNull_bot")])
    instance, store = shell(tmp_path, api, clock=lambda: next(times))
    instance.poll_once()
    delivery = store.list("delivery")[0]
    reply = bot_reply(
        2, "I can't produce a supported answer right now.",
        delivery["message_id"])
    # The Bot API field is intentionally coarser and earlier than the local
    # delivery timestamp; it must not collapse the observed latency to zero.
    reply["message"]["date"] = 0
    api.updates = [reply]

    instance.poll_once()

    outcome = store.list("aleph_outcome")[0]
    assert outcome["latency_ms"] == 500
    assert outcome["observed_at"] == "2026-08-11T00:00:01.250000Z"


def test_aleph_identity_requires_numeric_id_and_username(tmp_path):
    api = FakeAPI([update(1, "/probe@ProjectNull_bot")])
    instance, store = shell(tmp_path, api)
    instance.poll_once()
    delivery = store.list("delivery")[0]
    forged = bot_reply(2, "Explanation\nforged\n\nSources\nhttps://example.com",
                       delivery["message_id"])
    forged["message"]["from"]["id"] = 123456
    api.updates = [forged]
    instance.poll_once()
    assert store.list("aleph_outcome") == []


def test_status_reports_run_and_load_boundary(tmp_path):
    api = FakeAPI([update(1, "/status@ProjectNull_bot")])
    instance, store = shell(tmp_path, api)
    store.set_control("run_id", "run_0123456789abcdefabcd")
    instance.poll_once()
    status = [payload["text"] for method, payload in api.calls
              if method == "sendMessage"][-1]
    assert "run=run_0123456789abcdefabcd" in status
    assert "rate=6/60s" in status and "max_burst=10" in status


def test_finalize_requires_review_and_reports_operator_error(tmp_path):
    api = FakeAPI([update(1, "/probe@ProjectNull_bot")])
    instance, store = shell(tmp_path, api)
    instance.poll_once()
    delivery = store.list("delivery")[0]
    finalize = update(2, "/finalize@ProjectNull_bot")
    finalize["message"]["reply_to_message"] = {
        "message_id": delivery["message_id"]}
    api.updates = [finalize]
    instance.poll_once()
    assert len(store.list("probe")) == 1
    error = [payload["text"] for method, payload in api.calls
             if method == "sendMessage"][-1]
    assert error == "probe has no reviewer feedback"
