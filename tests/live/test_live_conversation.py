"""Live conversation tests, as the dedicated test end user."""

import pytest

from kbot_client import Client, chatbot_client
from kbot_client.callback_chat import AsyncCallbackChatClient
from kbot_client.chatbot_client import chat_client_2

pytestmark = pytest.mark.live

BYE = "Bye, hope to see you again soon"


def bot_texts(payloads: list) -> list[str]:
    """Text parts of the bot messages found in conversation payloads."""
    return [
        part["value"]
        for payload in payloads
        for message in payload.get("messages", [])
        if message.get("type") == "message"
        for part in message.get("parts", [])
        if part.get("format") == "text" and part.get("value")
    ]


def test_callback_chat_round_trip(user_client: Client):
    received: list = []
    chat = AsyncCallbackChatClient(user_client, "chat", callback=received.append, pull_interval=0.5, pull_timeout=10)
    try:
        assert chat.conversation_uuid
        assert received, "the greeting is passed to the callback"
        received.clear()

        chat.send("hello")
        chat.get_response()

        assert bot_texts(received), "the bot answered with some text"
        assert received[-1]["dialog_in_progress"] is False
        chat.close()
    finally:
        chat.delete()


def test_command_line_chatbot_session(user_client: Client, monkeypatch: pytest.MonkeyPatch, capsys):
    lines = ["hello"]

    def fake_input(_prompt: str = "") -> str:
        if not lines:
            raise EOFError
        return lines.pop(0)

    monkeypatch.setattr("builtins.input", fake_input)

    bot = chatbot_client.run(mode="synchronous", client=user_client, prompt="BOT[{sender}]: {message}")

    assert isinstance(bot, chat_client_2.SyncChatClient)
    output = capsys.readouterr().out.splitlines()
    assert output[-1] == BYE
    assert any(line.startswith("BOT[") for line in output[:-1]), output
