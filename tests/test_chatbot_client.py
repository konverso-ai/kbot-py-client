"""Tests for the interactive command line chatbots in kbot_client.chatbot_client."""

from collections.abc import Callable

import pytest

from kbot_client import Client, chatbot_client
from kbot_client.chatbot_client import chat_client, chat_client_2
from tests.fake_kbot import FakeKbot

BYE = "Bye, hope to see you again soon"

# Kbot <= 2024.01: messages carry a "message" list of parts.
V1_WELCOME = {
    "id": 5,
    "sender": {"name": "Kbot"},
    "messages": [{"type": "message", "message": [{"format": "text", "value": "Welcome"}]}],
}
# Kbot >= 2024.02: messages carry "parts".
V2_GREETING = {
    "sender": {"name": "Kbot"},
    "messages": [{"type": "message", "parts": [{"format": "text", "value": "Hello"}]}],
}


@pytest.fixture
def user_input(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Script the lines typed by the user; EOF (Ctrl-D) after the last one."""

    def script(*lines: str) -> None:
        pending = list(lines)

        def fake_input(_prompt: str = "") -> str:
            if not pending:
                raise EOFError
            return pending.pop(0)

        monkeypatch.setattr("builtins.input", fake_input)

    return script


@pytest.fixture
def server(kbot: FakeKbot) -> FakeKbot:
    kbot.route("POST", "/api/conversation/", V1_WELCOME)
    kbot.route("POST", "/api/conversation/chat/", {"id": "c-1"})
    kbot.route("POST", "/api/conversation/chat/greeting/", V2_GREETING)
    return kbot


def bot_message(parts_key: str, *parts: dict) -> dict:
    return {"type": "message", "sender": {"name": "Kbot"}, parts_key: list(parts)}


class TestRun:
    def test_requires_client(self):
        with pytest.raises(RuntimeError, match="Missing mandatory 'client'"):
            chatbot_client.run()

    @pytest.mark.parametrize(
        ("version", "mode", "expected"),
        [
            (None, "synchronous", chat_client.SyncChatClient),
            ("2023.12", "synchronous", chat_client.SyncChatClient),
            ("2024.01", "asynchronous", chat_client.AsyncChatClient),
            ("2024.02", "synchronous", chat_client_2.SyncChatClient),
            ("2025.10", "asynchronous", chat_client_2.AsyncChatClient),
            ("2025.10", "anything-else", chat_client_2.SyncChatClient),
        ],
    )
    def test_picks_implementation_from_version_and_mode(self, server, client: Client, user_input, version, mode, expected):
        client.version = version
        user_input()

        bot = chatbot_client.run(mode, client=client)

        assert type(bot) is expected


class TestChatClientV2:
    def test_sync_session(self, server: FakeKbot, client: Client, user_input, capsys):
        server.route(
            "GET",
            "/api/conversation/chat/c-1/messages/",
            {
                "dialog_in_progress": False,
                "messages": [
                    {"type": "typing"},
                    bot_message(
                        "parts",
                        {"format": "markdown", "value": "**Ful", "mode": "append"},
                        {"format": "markdown", "value": "**Full answer**"},
                        {"format": "image", "value": "chart.png"},
                    ),
                ],
            },
        )
        server.route("POST", "/api/conversation/chat/c-1/message/", {})
        user_input("", "What is Kbot?", "EXIT")

        chat_client_2.SyncChatClient(client)

        assert capsys.readouterr().out.splitlines() == ["Kbot> Hello", "Kbot> **Full answer**", BYE]
        (sent,) = server.requests_to("POST", "/api/conversation/chat/c-1/message/")
        assert sent.json()["message"] == "What is Kbot?"
        (poll,) = server.requests_to("GET", "/api/conversation/chat/c-1/messages/")
        assert poll.query == {"wait": ["true"]}

    def test_streaming_parts_are_shown_on_request(self, server: FakeKbot, client: Client, user_input, capsys):
        server.route(
            "GET",
            "/api/conversation/chat/c-1/messages/",
            {"dialog_in_progress": False, "messages": [bot_message("parts", {"format": "markdown", "value": "Ful", "mode": "append"})]},
        )
        server.route("POST", "/api/conversation/chat/c-1/message/", {})
        user_input("hi")

        chat_client_2.SyncChatClient(client, display_intro=False, show_streaming_parts=True)

        assert capsys.readouterr().out.splitlines() == ["Kbot> Ful", BYE]
        assert server.requests_to("POST", "/api/conversation/chat/greeting/") == []

    def test_async_polls_until_bot_waits_for_user(self, server: FakeKbot, client: Client, user_input, capsys):
        server.route(
            "GET",
            "/api/conversation/chat/c-1/messages/",
            {"dialog_in_progress": True, "messages": [bot_message("parts", {"format": "text", "value": "Which one?"})]},
            {"dialog_in_progress": True, "messages": [{"type": "wait_user_input", "sender": {"name": "Kbot"}}]},
        )
        server.route("POST", "/api/conversation/chat/c-1/message/", {})
        user_input("hi")

        chat_client_2.AsyncChatClient(client, pull_interval=0, pull_timeout=4, prompt="[{sender}] {message}")

        assert capsys.readouterr().out.splitlines() == ["[Kbot] Hello", "[Kbot] Which one?", BYE]
        polls = server.requests_to("GET", "/api/conversation/chat/c-1/messages/")
        assert [p.query for p in polls] == [{"timeout": ["4"]}] * 2


class TestChatClientV1:
    def test_sync_session(self, server: FakeKbot, client: Client, user_input, capsys):
        server.route(
            "GET",
            "/api/conversation/5/messages/",
            {"dialog_in_progress": False, "messages": [bot_message("message", {"format": "html", "value": "<b>Hi</b>"})]},
        )
        server.route("POST", "/api/conversation/5/message/", {})
        user_input("hello", "stop")

        chat_client.SyncChatClient(client, assistant="a-1")

        assert capsys.readouterr().out.splitlines() == ["Kbot> Welcome", "Kbot> <b>Hi</b>", BYE]
        (created,) = server.requests_to("POST", "/api/conversation/")
        assert created.json() == {"username": "bot", "assistant": "a-1"}
        (sent,) = server.requests_to("POST", "/api/conversation/5/message/")
        body = sent.json()
        assert body.pop("message_id")
        assert body == {"conversation_id": 5, "type": "message", "message": "hello", "assistant": "a-1"}

    def test_render_types_filter_displayed_parts(self, server: FakeKbot, client: Client, user_input, capsys):
        user_input()

        chat_client.SyncChatClient(client, render_types=("html",))

        assert capsys.readouterr().out.splitlines() == [BYE]

    def test_async_polls_until_dialog_ends(self, server: FakeKbot, client: Client, user_input, capsys):
        server.route(
            "GET",
            "/api/conversation/5/messages/",
            {"dialog_in_progress": True, "messages": [bot_message("message", {"format": "text", "value": "One"})]},
            {"dialog_in_progress": False, "messages": [bot_message("message", {"format": "text", "value": "Two"})]},
        )
        server.route("POST", "/api/conversation/5/message/", {})
        user_input("hi")

        chat_client.AsyncChatClient(client, pull_interval=0)

        assert capsys.readouterr().out.splitlines() == ["Kbot> Welcome", "Kbot> One", "Kbot> Two", BYE]
        assert len(server.requests_to("GET", "/api/conversation/5/messages/")) == 2
