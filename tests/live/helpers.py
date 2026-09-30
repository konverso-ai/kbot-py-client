"""Constants and helpers shared by the live tests."""

from kbot_client import Recorder

# Dedicated end user, created on first run through user/lookup_create.
TEST_USER = "kbot-py-client-tests@konverso.ai"
TEST_EXTERNAL_AUTH = "kbot-py-client-tests"

CHAT_DATA = {"username": "bot", "type": "chat", "assistant_id": None}


class ListRecorder(Recorder):
    """Keeps every recorded call as ``(method, url, headers, status)``."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict, int]] = []

    def record(self, method, url, headers=None, data=None, files=None, response=None):  # noqa: ARG002
        assert headers is not None
        assert response is not None
        self.calls.append((method, url, headers, response.status_code))
