"""Tests for kbot_client.client.Client against a local fake Kbot server."""

from typing import Any

import pytest
import requests

import kbot_client.client
from kbot_client import Client, DownKbotClient

from tests.fake_kbot import API_KEY, FakeKbot


def schema_with(*endpoints: dict) -> dict:
    return {"version": "2024.02", "endpoints": list(endpoints)}


def field(name: str, type_: str = "str", *, mandatory: bool = False, default=None) -> dict:
    return {"name": name, "type": type_, "mandatory": mandatory, "default": default}


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kbot_client.client.time, "sleep", lambda _seconds: None)


class TestUrls:
    @pytest.mark.parametrize(
        ("port", "expected"),
        [
            (443, "https://kbot.example"),
            (80, "http://kbot.example"),
            (8443, "https://kbot.example:8443"),
            (8080, "http://kbot.example:8080"),
            ("443", "https://kbot.example:443"),
        ],
    )
    def test_scheme_and_port_derive_from_port(self, port, expected):
        cli = Client("kbot.example", port=port)

        assert cli.url == expected

    def test_derived_urls(self):
        cli = Client("kbot.example")

        assert cli.admin_url == "https://kbot.example/admin"
        assert cli.chat_url == "https://kbot.example"
        assert cli.avatar_url == "https://kbot.example/images/kbot_avatar.png"

    def test_no_request_without_credentials(self, kbot: FakeKbot):
        Client("127.0.0.1", port=kbot.port)

        assert kbot.requests == []

    def test_down_client_keeps_error_and_does_not_connect(self, kbot: FakeKbot):
        down = DownKbotClient("127.0.0.1", port=kbot.port, error="connection refused")

        assert down.error == "connection refused"
        assert kbot.requests == []


class TestApiKeyAuthentication:
    def test_schema_is_fetched_with_api_key(self, kbot: FakeKbot, client: Client):
        (schema_request,) = kbot.requests_to("GET", "/api/schema/")

        assert schema_request.headers["X-API-KEY"] == API_KEY
        assert schema_request.headers["Content-Type"] == "application/json; charset=utf-8"
        assert client.version == "2024.02"

    def test_invalid_api_key_raises(self, kbot: FakeKbot):
        kbot.route("GET", "/api/schema/", (403, {"error": "forbidden"}))

        with pytest.raises(requests.HTTPError):
            Client("127.0.0.1", port=kbot.port, api_key="bad")


class TestLogin:
    @pytest.mark.usefixtures("logged_in_client")
    def test_login_sends_credentials_then_uses_access_token(self, kbot: FakeKbot):
        (login_request,) = kbot.requests_to("POST", "/api/login")
        (schema_request,) = kbot.requests_to("GET", "/api/schema/")

        assert login_request.json() == {"username": "alice", "usertype": "local", "password": "secret"}
        assert schema_request.headers["Authorization"] == "access-1"
        assert "X-API-KEY" not in schema_request.headers

    def test_login_without_password_uses_username(self, kbot: FakeKbot, capsys):
        kbot.route("POST", "/api/login", {"access_token": "t"})
        cli = Client("127.0.0.1", port=kbot.port)

        cli.login("alice")

        (login_request,) = kbot.requests_to("POST", "/api/login")
        assert login_request.json()["password"] == "alice"
        assert "Password is not set" in capsys.readouterr().out

    def test_rejected_login_raises(self, kbot: FakeKbot):
        kbot.route("POST", "/api/login", (401, {"error": "bad credentials"}))
        cli = Client("127.0.0.1", port=kbot.port)

        with pytest.raises(requests.HTTPError):
            cli.login("alice", "wrong")

        assert kbot.requests_to("GET", "/api/schema/") == []

    def test_logout_is_noop_when_not_logged_in(self, kbot: FakeKbot):
        cli = Client("127.0.0.1", port=kbot.port)

        cli.logout()

        assert kbot.requests == []


class TestImpersonate:
    def test_impersonate_switches_from_api_key_to_user_token(self, kbot: FakeKbot, client: Client):
        kbot.route("POST", "/api/user/impersonate/", {"access_token": "bob-token", "user_id": "bob"})

        client.impersonate("bob", usertype="ldap", userdata={"team": "it"})

        (impersonate_request,) = kbot.requests_to("POST", "/api/user/impersonate/")
        assert impersonate_request.json() == {
            "username": "bob",
            "im_type": "ldap",
            "external_auth": "",
            "userdata": {"team": "it"},
        }
        last_schema_request = kbot.requests_to("GET", "/api/schema/")[-1]
        assert last_schema_request.headers["Authorization"] == "bob-token"
        assert "X-API-KEY" not in last_schema_request.headers

    def test_failed_impersonation_raises(self, kbot: FakeKbot, client: Client):
        kbot.route("POST", "/api/user/impersonate/", (403, {}))

        with pytest.raises(requests.HTTPError):
            client.impersonate("bob")


class TestRestMethods:
    @pytest.mark.parametrize("verb", ["post", "put"])
    def test_body_is_sent_as_json(self, kbot: FakeKbot, client: Client, verb):
        kbot.route(verb, "/api/user/", {"ok": True})

        response = getattr(client, verb)("user", data={"name": "alice", "tags": [1, 2]})

        assert response.json() == {"ok": True}
        (request,) = kbot.requests_to(verb, "/api/user/")
        assert request.json() == {"name": "alice", "tags": [1, 2]}

    @pytest.mark.parametrize("verb", ["get", "delete"])
    def test_params_are_sent_as_query_string(self, kbot: FakeKbot, client: Client, verb):
        kbot.route(verb, "/api/user/", {})

        getattr(client, verb)("user", params={"id": 3, "q": "a b"})

        (request,) = kbot.requests_to(verb, "/api/user/")
        assert request.query == {"id": ["3"], "q": ["a b"]}

    def test_request_accepts_explicit_method(self, kbot: FakeKbot, client: Client):
        kbot.route("PATCH", "/api/user/1/", {})

        client.request("patch", "user/1", data={"a": 1})

        (request,) = kbot.requests_to("PATCH", "/api/user/1/")
        assert request.json() == {"a": 1}

    def test_post_file_sends_multipart_and_keeps_json_headers(self, kbot: FakeKbot, client: Client, tmp_path):
        kbot.route("POST", "/api/attachment/", {"id": "file-1"})
        kbot.route("GET", "/api/user/", {})
        document = tmp_path / "doc.pdf"
        document.write_bytes(b"%PDF-content")

        with document.open("rb") as fd:
            client.post_file(
                "attachment",
                data={"folder": "F1", "name": "doc.pdf"},
                params={"override": False},
                files={"upload_files": ("doc.pdf", fd, "application/pdf")},
            )
        client.get("user")

        (upload,) = kbot.requests_to("POST", "/api/attachment/")
        assert upload.headers["Content-Type"].startswith("multipart/form-data")
        assert upload.headers["Accept"] == "*/*"
        assert upload.headers["X-API-KEY"] == API_KEY
        assert upload.query == {"override": ["False"]}
        assert upload.form() == {
            "folder": (None, b"F1"),
            "name": (None, b"doc.pdf"),
            "upload_files": ("doc.pdf", b"%PDF-content"),
        }
        # The multipart header override must not leak into later requests.
        (follow_up,) = kbot.requests_to("GET", "/api/user/")
        assert follow_up.headers["Content-Type"] == "application/json; charset=utf-8"


class TestUnit:
    def test_returns_json_on_success(self, kbot: FakeKbot, client: Client):
        kbot.route("GET", "/api/metric/", {"count": 4})

        assert client.unit("metric", params={"period": "day"}) == {"count": 4}
        assert kbot.requests_to("GET", "/api/metric/")[0].query == {"period": ["day"]}

    @pytest.mark.parametrize("status", [404, 500])
    def test_returns_none_on_error_status(self, kbot: FakeKbot, client: Client, status):
        kbot.route("GET", "/api/metric/", (status, {"error": "x"}))

        assert client.unit("metric") is None


class TestSchemaEndpoints:
    def test_positional_args_fill_the_path(self, kbot: FakeKbot):
        kbot.route(
            "GET",
            "/api/schema/",
            schema_with({"method": "get", "name": "get_dashboard", "path": "dashboard/%s", "params": [], "data": []}),
        )
        kbot.route("GET", "/api/dashboard/7/", {"id": 7})
        cli: Any = Client("127.0.0.1", port=kbot.port, api_key=API_KEY)

        assert cli.get_dashboard(7).json() == {"id": 7}

    def test_kwargs_are_split_into_params_and_data_with_defaults(self, kbot: FakeKbot):
        kbot.route(
            "GET",
            "/api/schema/",
            schema_with(
                {
                    "method": "post",
                    "name": "conversation",
                    "path": "conversation",
                    "params": [field("lang", default="en"), field("debug", "bool")],
                    "data": [field("username", mandatory=True), field("limit", "int", default=10)],
                    "description": "Create a conversation",
                }
            ),
        )
        kbot.route("POST", "/api/conversation/", {"id": 1})
        cli: Any = Client("127.0.0.1", port=kbot.port, api_key=API_KEY)

        cli.conversation(username="bot", limit=3)

        (request,) = kbot.requests_to("POST", "/api/conversation/")
        assert request.query == {"lang": ["en"]}
        assert request.json() == {"username": "bot", "limit": 3}
        assert cli.conversation.__doc__ == "Create a conversation"

    def test_missing_mandatory_argument_raises_before_request(self, kbot: FakeKbot):
        kbot.route(
            "GET",
            "/api/schema/",
            schema_with({"method": "post", "name": "conversation", "path": "conversation",
                         "params": [], "data": [field("username", mandatory=True)]}),
        )
        cli: Any = Client("127.0.0.1", port=kbot.port, api_key=API_KEY)

        with pytest.raises(RuntimeError, match="Missed attribute 'username' in 'data'"):
            cli.conversation()

        assert kbot.requests_to("POST", "/api/conversation/") == []

    def test_wrongly_typed_argument_raises(self, kbot: FakeKbot):
        kbot.route(
            "GET",
            "/api/schema/",
            schema_with({"method": "get", "name": "metric", "path": "metric",
                         "params": [field("limit", "int")], "data": []}),
        )
        cli: Any = Client("127.0.0.1", port=kbot.port, api_key=API_KEY)

        with pytest.raises(RuntimeError, match="Invalid type of attribute 'limit'"):
            cli.metric(limit="10")

    def test_schema_endpoint_does_not_override_schema_method(self, kbot: FakeKbot):
        kbot.route(
            "GET",
            "/api/schema/",
            schema_with({"method": "get", "name": "schema", "path": "other", "params": [], "data": []}),
        )
        cli: Any = Client("127.0.0.1", port=kbot.port, api_key=API_KEY)

        cli.schema()

        assert len(kbot.requests_to("GET", "/api/schema/")) == 2
        assert kbot.requests_to("GET", "/api/other/") == []


class TestTokenRefresh:
    def test_expired_token_is_refreshed_and_request_replayed(self, kbot: FakeKbot, logged_in_client: Client):
        kbot.route("GET", "/api/metric/", (401, {}), {"count": 1})
        kbot.route("POST", "/api/refresh", {"access_token": "access-2"})

        response = logged_in_client.get("metric", params={"p": "1"})

        assert response.status_code == 200
        assert response.json() == {"count": 1}
        (refresh,) = kbot.requests_to("POST", "/api/refresh")
        assert refresh.json() == {"refresh_token": "refresh-1"}
        first, replay = kbot.requests_to("GET", "/api/metric/")
        assert first.headers["Authorization"] == "access-1"
        assert replay.headers["Authorization"] == "access-2"
        assert replay.query == {"p": ["1"]}

    @pytest.mark.usefixtures("no_sleep")
    def test_gives_up_after_three_failed_refreshes(self, kbot: FakeKbot, logged_in_client: Client):
        kbot.route("GET", "/api/metric/", (401, {}))
        kbot.route("POST", "/api/refresh", (401, {}))

        with pytest.raises(requests.HTTPError):
            logged_in_client.get("metric")

        assert len(kbot.requests_to("GET", "/api/metric/")) == 4
        assert len(kbot.requests_to("POST", "/api/refresh")) == 4


class TestMessage:
    @pytest.mark.parametrize("final_event", ["stop_topic", "wait_user_input"])
    def test_polls_until_bot_stops_and_collects_messages(self, kbot: FakeKbot, client: Client, final_event):
        kbot.route("POST", "/api/conversation/42/message/", {})
        kbot.route(
            "GET",
            "/api/conversation/42/",
            [{"type": "message", "message": "Hello"}],
            [{"type": "typing"}, {"type": "message", "message": "How can I help?"}, {"type": final_event}],
        )

        messages = client.message(42, "hi")

        assert messages == [
            {"type": "message", "message": "Hello"},
            {"type": "message", "message": "How can I help?"},
        ]
        (sent,) = kbot.requests_to("POST", "/api/conversation/42/message/")
        assert sent.json() == {"type": "message", "message": "hi"}
        assert len(kbot.requests_to("GET", "/api/conversation/42/")) == 2

    def test_rejected_message_raises(self, kbot: FakeKbot, client: Client):
        kbot.route("POST", "/api/conversation/42/message/", (404, {}))

        with pytest.raises(requests.HTTPError):
            client.message(42, "hi")
