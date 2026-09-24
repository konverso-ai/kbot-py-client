"""Tests for kbot_client.callback_chat.AsyncCallbackChatClient."""

import pytest
import requests

from kbot_client import Client
from kbot_client.callback_chat import AsyncCallbackChatClient
from tests.fake_kbot import FakeKbot

GREETING = {"sender": {"name": "Kbot"}, "messages": [{"type": "message", "parts": [{"format": "text", "value": "Hi"}]}]}
CONVERSATION = "/api/conversation/agentic/conv-1"


@pytest.fixture
def conversation(kbot: FakeKbot) -> FakeKbot:
    kbot.route("POST", "/api/conversation/agentic/greeting/", GREETING)
    kbot.route("POST", "/api/conversation/agentic/", {"id": "conv-1"})
    return kbot


@pytest.fixture
def received() -> list:
    return []


@pytest.fixture
def chat(conversation: FakeKbot, client: Client, received: list) -> AsyncCallbackChatClient:
    return AsyncCallbackChatClient(client, "agentic", assistant="a-1", callback=received.append, pull_interval=0, pull_timeout=3)


class TestCreation:
    def test_greets_then_creates_conversation(self, conversation: FakeKbot, chat: AsyncCallbackChatClient, received: list):
        expected_body = {"username": "bot", "type": "agentic", "assistant_id": "a-1"}

        assert chat.conversation_uuid == "conv-1"
        assert received == [GREETING]
        assert [r.json() for r in conversation.requests_to("POST", "/api/conversation/agentic/greeting/")] == [expected_body]
        assert [r.json() for r in conversation.requests_to("POST", "/api/conversation/agentic/")] == [expected_body]

    def test_without_intro_skips_greeting(self, conversation: FakeKbot, client: Client, received: list):
        chat = AsyncCallbackChatClient(client, "agentic", callback=received.append, display_intro=False)

        assert chat.conversation_uuid == "conv-1"
        assert received == []
        assert conversation.requests_to("POST", "/api/conversation/agentic/greeting/") == []

    def test_failed_creation_raises(self, kbot: FakeKbot, client: Client):
        kbot.route("POST", "/api/conversation/agentic/", (500, {}))

        with pytest.raises(requests.HTTPError):
            AsyncCallbackChatClient(client, "agentic", callback=print, display_intro=False)


class TestExchange:
    def test_send_posts_user_message(self, conversation: FakeKbot, chat: AsyncCallbackChatClient):
        conversation.route("POST", CONVERSATION + "/message/", {})

        chat.send("What is Kbot?")

        (request,) = conversation.requests_to("POST", CONVERSATION + "/message/")
        body = request.json()
        assert body.pop("message_id")
        assert body == {"type": "message", "message": "What is Kbot?", "status": "sending", "fromUser": True}

    def test_attach_uploads_file_with_its_real_name(self, conversation: FakeKbot, chat: AsyncCallbackChatClient, tmp_path):
        conversation.route("POST", CONVERSATION + "/message/", {})
        path = tmp_path / "tmp123.doc"
        path.write_bytes(b"status")

        chat.attach("Daily Status.doc", str(path))

        (request,) = conversation.requests_to("POST", CONVERSATION + "/message/")
        assert request.form() == {
            "message": (None, b"Daily Status.doc"),
            "type": (None, b"attachment"),
            "file": ("Daily Status.doc", b"status"),
        }

    def test_get_response_polls_until_dialog_ends(self, conversation: FakeKbot, chat: AsyncCallbackChatClient, received: list):
        chunks = [
            {"dialog_in_progress": True, "messages": [{"type": "typing"}]},
            {"dialog_in_progress": True, "messages": [{"type": "message", "parts": []}]},
            {"dialog_in_progress": False, "messages": []},
        ]
        conversation.route("GET", CONVERSATION + "/messages/", *chunks)
        received.clear()

        chat.get_response()

        assert received == chunks
        polls = conversation.requests_to("GET", CONVERSATION + "/messages/")
        assert [p.query for p in polls] == [{"timeout": ["3"]}] * 3

    @pytest.mark.parametrize(("method", "path", "action"), [
        ("POST", CONVERSATION + "/close/", AsyncCallbackChatClient.close),
        ("DELETE", CONVERSATION + "/", AsyncCallbackChatClient.delete),
    ])
    def test_close_and_delete_hit_conversation(self, conversation: FakeKbot, chat, method, path, action):
        conversation.route(method, path, {})

        action(chat)

        assert len(conversation.requests_to(method, path)) == 1

    @pytest.mark.parametrize("action", [AsyncCallbackChatClient.close, AsyncCallbackChatClient.delete])
    def test_close_and_delete_raise_on_error(self, chat, action):
        with pytest.raises(requests.HTTPError):
            action(chat)
