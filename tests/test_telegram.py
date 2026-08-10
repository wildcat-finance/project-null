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


def shell(tmp_path, api):
    store = Store(str(tmp_path / "null.db"))
    instance = TelegramShell(
        store, Generator(clock=lambda: NOW), api,
        aleph_username="ProjectAlephWildcat_bot",
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
    duplicate = update(4, "/probe")
    api = FakeAPI([duplicate, duplicate])
    instance, store = shell(tmp_path, api)
    instance.poll_once()
    probe_sends = [payload for method, payload in api.calls
                   if method == "sendMessage" and payload["text"].startswith("/ask@")]
    assert len(probe_sends) == 1


def test_pause_mode_burst_and_loop_prevention(tmp_path):
    api = FakeAPI([
        update(1, "/mode false_premise"), update(2, "/pause"),
        update(3, "/burst 2"), update(4, "/resume"),
        update(5, "/burst 2"), update(6, "/probe", user=99),
        update(7, "/probe", user=8728174629, bot=True),
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
        update(2, "please make a probe"),
    ])
    instance, store = shell(tmp_path, api)
    instance.poll_once()
    assert store.list("probe") == []
