"""Regression tests for bugs found while adding the test suite.

Each bug has two kinds of tests:
- "expected" tests assert the correct behavior (they must pass);
- "symptom" tests assert the buggy behavior is gone (the bug must not reappear).
All of them failed before the fix.
"""

import threading
from collections.abc import Iterator

import pytest
import requests

from kbot_client import Client, Recorder
from kbot_client.callback_chat import AsyncCallbackChatClient
from tests.fake_kbot import API_KEY, FakeKbot


@pytest.fixture
def release() -> Iterator[threading.Event]:
    """Event unblocking slow server replies, set at teardown at the latest."""
    event = threading.Event()
    yield event
    event.set()


def slow_reply(release: threading.Event):
    def reply(_request):
        release.wait(timeout=2)
        return {}

    return reply


class TestLogoutUrl:
    """Bug: logout() passed the absolute URL as a unit, hitting /api/http://host/api/logout/."""

    def test_expected_logout_posts_token_to_logout_endpoint(self, kbot: FakeKbot, logged_in_client: Client):
        kbot.route("POST", "/api/logout", {})

        logged_in_client.logout()

        (request,) = kbot.requests_to("POST", "/api/logout")
        assert request.headers["Authorization"] == "access-1"

    def test_expected_logout_honours_timeout(self, kbot: FakeKbot, logged_in_client: Client, release):
        kbot.route("POST", "/api/logout", slow_reply(release))

        with pytest.raises(requests.Timeout):
            logged_in_client.logout(timeout=0.2)

    def test_symptom_base_url_is_never_embedded_in_path(self, kbot: FakeKbot, logged_in_client: Client):
        kbot.route("POST", "/api/logout", {})

        logged_in_client.logout()

        assert [r.path for r in kbot.requests if "http" in r.path] == []


class TestReplayAfterTokenRefresh:
    """Bug: the request replayed after a 401 + token refresh dropped `files` and `timeout`."""

    @pytest.fixture
    def expiring(self, kbot: FakeKbot) -> FakeKbot:
        kbot.route("POST", "/api/refresh", {"access_token": "access-2"})
        kbot.route("POST", "/api/attachment/", (401, {}), {"id": "file-1"})
        return kbot

    @pytest.mark.parametrize("as_tuple", [False, True], ids=["file-object", "tuple"])
    def test_expected_upload_is_replayed_with_whole_file(self, expiring: FakeKbot, logged_in_client: Client, tmp_path, as_tuple):
        document = tmp_path / "doc.txt"
        document.write_bytes(b"hello")

        with document.open("rb") as fd:
            upload = ("doc.txt", fd, "text/plain") if as_tuple else fd
            response = logged_in_client.post_file("attachment", data={"name": "doc.txt"}, files={"upload_files": upload})

        assert response.json() == {"id": "file-1"}
        first, replay = expiring.requests_to("POST", "/api/attachment/")
        assert replay.headers["Authorization"] == "access-2"
        assert replay.form() == first.form() == {
            "name": (None, b"doc.txt"),
            "upload_files": ("doc.txt", b"hello"),
        }

    def test_expected_replay_honours_timeout(self, kbot: FakeKbot, logged_in_client: Client, release):
        kbot.route("POST", "/api/refresh", {"access_token": "access-2"})
        kbot.route("GET", "/api/metric/", (401, {}), slow_reply(release))

        with pytest.raises(requests.Timeout):
            logged_in_client.get("metric", timeout=0.2)

    def test_symptom_upload_replay_is_not_sent_as_json(self, expiring: FakeKbot, logged_in_client: Client, tmp_path):
        document = tmp_path / "doc.txt"
        document.write_bytes(b"hello")

        with document.open("rb") as fd:
            logged_in_client.post_file("attachment", data={"name": "doc.txt"}, files={"upload_files": fd})

        replay = expiring.requests_to("POST", "/api/attachment/")[-1]
        assert not replay.headers["Content-Type"].startswith("application/json")
        assert replay.body != b'{"name": "doc.txt"}'


class ListRecorder(Recorder):
    """Keeps the headers objects it receives, without copying them."""

    def __init__(self) -> None:
        self.headers: list[dict] = []

    def record(self, method, url, headers=None, data=None, files=None, response=None):  # noqa: ARG002
        assert headers is not None
        self.headers.append(headers)


class MaskingRecorder(Recorder):
    """Hides secrets in the headers it receives, as a logging recorder would."""

    def record(self, method, url, headers=None, data=None, files=None, response=None):  # noqa: ARG002
        assert headers is not None
        for secret in ("X-API-KEY", "Authorization"):
            if secret in headers:
                headers[secret] = "***"


class TestRecorderHeaders:
    """Bug: the recorder received the client's live headers dict instead of a snapshot."""

    def test_expected_recorded_headers_are_those_sent(self, kbot: FakeKbot, logged_in_client: Client):
        kbot.route("GET", "/api/metric/", (401, {}), {"count": 1})
        kbot.route("POST", "/api/refresh", {"access_token": "access-2"})
        recorder = ListRecorder()
        logged_in_client.recorder = recorder

        logged_in_client.get("metric")

        assert [h["Authorization"] for h in recorder.headers] == ["access-1", "access-2"]

    def test_symptom_recorder_cannot_alter_client_credentials(self, kbot: FakeKbot):
        kbot.route("GET", "/api/metric/", {})
        cli = Client("127.0.0.1", port=kbot.port, api_key=API_KEY, recorder=MaskingRecorder())

        cli.get("metric")

        (request,) = kbot.requests_to("GET", "/api/metric/")
        assert request.headers["X-API-KEY"] == API_KEY


class TestCallbackChatWithoutCallback:
    """Bug: `callback` defaults to None but was called unconditionally (TypeError)."""

    @pytest.fixture
    def conversation(self, kbot: FakeKbot) -> FakeKbot:
        kbot.route("POST", "/api/conversation/chat/greeting/", {"messages": []})
        kbot.route("POST", "/api/conversation/chat/", {"id": "c-1"})
        kbot.route("POST", "/api/conversation/chat/c-1/message/", {})
        kbot.route("GET", "/api/conversation/chat/c-1/messages/", {"dialog_in_progress": False, "messages": []})
        return kbot

    def test_expected_conversation_runs_without_callback(self, conversation: FakeKbot, client: Client):
        chat = AsyncCallbackChatClient(client, "chat", pull_interval=0)

        chat.send("hello")
        chat.get_response()

        assert chat.conversation_uuid == "c-1"
        assert len(conversation.requests_to("GET", "/api/conversation/chat/c-1/messages/")) == 1

    def test_symptom_creation_with_intro_does_not_raise_type_error(self, conversation: FakeKbot, client: Client):
        try:
            AsyncCallbackChatClient(client, "chat", display_intro=True)
        except TypeError as error:
            pytest.fail("creating a chat without callback raised %r" % error)
