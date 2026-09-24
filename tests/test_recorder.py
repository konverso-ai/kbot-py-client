"""Tests for kbot_client.recorder and its integration with Client."""

import shlex
from dataclasses import dataclass
from typing import Any

import pytest
import requests

from kbot_client import Client, CurlPrinter, Printer, Recorder
from tests.fake_kbot import API_KEY, FakeKbot


@dataclass
class Call:
    method: str
    url: str
    headers: Any
    data: Any
    files: Any
    response: Any


class ListRecorder(Recorder):
    """Keeps every recorded call, as a user-defined recorder would."""

    def __init__(self) -> None:
        self.calls: list[Call] = []

    def record(self, method, url, headers=None, data=None, files=None, response=None):
        self.calls.append(Call(method, url, headers, data, files, response))


@pytest.fixture
def recorder() -> ListRecorder:
    return ListRecorder()


class TestClientRecording:
    def test_schema_call_at_creation_is_recorded(self, kbot: FakeKbot, recorder: ListRecorder):
        Client("127.0.0.1", port=kbot.port, api_key=API_KEY, recorder=recorder)

        (call,) = recorder.calls
        assert call.method == "get"
        assert call.url == "http://127.0.0.1:%s/api/schema/" % kbot.port
        assert call.headers["X-API-KEY"] == API_KEY
        assert call.response.json() == {"version": "2024.02", "endpoints": []}

    def test_records_full_url_raw_data_and_response(self, kbot: FakeKbot, client: Client, recorder: ListRecorder):
        kbot.route("POST", "/api/user/", (201, {"id": 1}))
        client.recorder = recorder

        client.post("user", data={"name": "alice"}, params={"dry": "1", "q": "a b"})

        (call,) = recorder.calls
        assert call.method == "post"
        assert call.url == "http://127.0.0.1:%s/api/user/?dry=1&q=a+b" % kbot.port
        assert call.data == {"name": "alice"}
        assert call.files is None
        assert call.response.status_code == 201

    def test_file_upload_records_multipart_headers(self, kbot: FakeKbot, client: Client, recorder: ListRecorder, tmp_path):
        kbot.route("POST", "/api/attachment/", {})
        client.recorder = recorder
        document = tmp_path / "doc.txt"
        document.write_bytes(b"x")

        with document.open("rb") as fd:
            client.post_file("attachment", data={"name": "doc.txt"}, files={"upload_files": fd})

        (call,) = recorder.calls
        assert "Content-Type" not in call.headers
        assert call.headers["Accept"] == "*/*"
        assert list(call.files) == ["upload_files"]

    def test_unauthorized_attempt_and_replay_are_both_recorded(self, kbot: FakeKbot, logged_in_client: Client, recorder: ListRecorder):
        kbot.route("GET", "/api/metric/", (401, {}), {"count": 1})
        kbot.route("POST", "/api/refresh", {"access_token": "access-2"})
        logged_in_client.recorder = recorder

        logged_in_client.get("metric")

        assert [c.response.status_code for c in recorder.calls] == [401, 200]

    def test_curl_printer_prints_replayable_command(self, kbot: FakeKbot, client: Client, capsys):
        kbot.route("GET", "/api/metric/", {})
        client.recorder = CurlPrinter()

        client.get("metric", params={"period": "day"})

        assert shlex.split(capsys.readouterr().out) == [
            "curl", "-X", "GET",
            "-H", "Content-Type: application/json; charset=utf-8",
            "-H", "X-API-KEY: %s" % API_KEY,
            "http://127.0.0.1:%s/api/metric/?period=day" % kbot.port,
        ]


def make_response(status: int, text: str) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = text.encode()  # noqa: SLF001
    response.encoding = "utf-8"
    return response


class TestPrinter:
    def test_prints_every_part_of_the_call(self, capsys):
        Printer().record(
            "post",
            "https://kbot.example/api/attachment/",
            headers={"Accept": "*/*"},
            data={"name": "doc.txt"},
            files={"upload_files": object()},
            response=make_response(200, '{"id": 1}'),
        )

        assert capsys.readouterr().out.splitlines() == [
            "POST https://kbot.example/api/attachment/ (https)",
            "  headers: {'Accept': '*/*'}",
            "  payload: {'name': 'doc.txt'}",
            "  files: ['upload_files']",
            '  -> 200 {"id": 1}',
        ]

    def test_omits_absent_parts(self, capsys):
        Printer().record("get", "http://kbot.example/api/metric/")

        assert capsys.readouterr().out.splitlines() == ["GET http://kbot.example/api/metric/ (http)"]

    def test_prints_error_responses(self, capsys):
        Printer().record("get", "http://kbot.example/api/x/", response=make_response(404, "not found"))

        assert capsys.readouterr().out.splitlines()[-1] == "  -> 404 not found"


class TestCurlPrinter:
    def test_json_body_is_serialized(self):
        command = CurlPrinter.to_curl(
            "post",
            "https://kbot.example/api/user/",
            headers={"Authorization": "tok en"},
            data={"name": "O'Brien"},
        )

        assert shlex.split(command) == [
            "curl", "-X", "POST",
            "-H", "Authorization: tok en",
            "-d", '{"name": "O\'Brien"}',
            "https://kbot.example/api/user/",
        ]

    def test_string_body_is_sent_verbatim(self):
        command = CurlPrinter.to_curl("put", "https://kbot.example/api/x/", data='{"raw": true}')

        assert shlex.split(command)[-3:] == ["-d", '{"raw": true}', "https://kbot.example/api/x/"]

    @pytest.mark.parametrize("data", [None, {}, ""])
    def test_empty_body_is_omitted(self, data):
        command = CurlPrinter.to_curl("get", "https://kbot.example/api/x/", data=data)

        assert shlex.split(command) == ["curl", "-X", "GET", "https://kbot.example/api/x/"]

    def test_files_switch_to_form_fields(self):
        command = CurlPrinter.to_curl(
            "post",
            "https://kbot.example/api/attachment/?override=False",
            data={"folder": "F1", "name": "my doc.pdf"},
            files={"upload_files": object()},
        )

        assert shlex.split(command) == [
            "curl", "-X", "POST",
            "-F", "upload_files=@<file>",
            "-F", "folder=F1",
            "-F", "name=my doc.pdf",
            "https://kbot.example/api/attachment/?override=False",
        ]

    def test_url_with_query_string_is_shell_quoted(self):
        command = CurlPrinter.to_curl("get", "https://kbot.example/api/x/?a=1&b=2")

        assert command.endswith("'https://kbot.example/api/x/?a=1&b=2'")
