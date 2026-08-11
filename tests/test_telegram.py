import json

from project_null.generator import Generator
from project_null.store import Store
from project_null.telegram import TelegramShell

NOW = "2026-08-11T00:00:00Z"


class FakeAPI:
    def __init__(self, updates=()):
        self.updates = list(updates)
        self.calls = []
        self.next_message = 100

    def call(self, method, payload=None):
        self.calls.append((method, payload or {}))
        if method == "getMe":
            return {"id": 9, "username": "ProjectNull_bot",
                    "can_read_all_group_messages": False}
        if method == "getWebhookInfo":
            return {"url": ""}
        if method == "getUpdates":
            offset = payload["offset"]
            return [item for item in self.updates if item["update_id"] >= offset]
        if method == "sendMessage":
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


def shell(tmp_path, api):
    store = Store(str(tmp_path / "null.db"))
    instance = TelegramShell(
        store, Generator(clock=lambda: NOW), api,
        aleph_username="ProjectAlephWildcat_bot",
        aleph_bot_id=8728174629,
        allowed_chat_ids={-100}, operator_user_ids={7}, clock=lambda: NOW)
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
