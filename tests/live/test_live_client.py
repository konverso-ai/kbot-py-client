"""Live tests of Client (authentication, REST calls, recorders) on a real Kbot."""

import json
import re
import shlex
import shutil
import subprocess
import uuid
from typing import Any

import pytest
import requests

from kbot_client import Client, CurlPrinter
from tests.live.helpers import CHAT_DATA, ListRecorder

pytestmark = pytest.mark.live


class TestAuthentication:
    def test_api_key_client_loads_schema(self, live_client: Client):
        cli: Any = live_client

        assert re.fullmatch(r"\d{4}\.\d{2}", cli.version)
        assert callable(cli.get_dashboard)

    @pytest.mark.usefixtures("no_sleep")
    def test_invalid_api_key_is_rejected(self, live_host: str):
        with pytest.raises(requests.HTTPError) as error:
            Client(live_host, api_key=str(uuid.uuid4()))

        response = error.value.response
        assert response is not None
        assert response.status_code == 401

    def test_api_key_account_cannot_chat(self, live_client: Client):
        response = live_client.post("conversation/chat/greeting", data=CHAT_DATA)

        assert response.status_code == 400
        assert "local" in response.json()["detail"]

    def test_impersonated_user_can_chat(self, user_client: Client):
        response = user_client.post("conversation/chat/greeting", data=CHAT_DATA)

        assert response.status_code == 200
        assert "X-API-KEY" not in response.request.headers

    def test_expired_access_token_is_refreshed(self, user_client: Client):
        recorder = ListRecorder()
        user_client.recorder = recorder
        # Simulate an expired access token: the server answers 401.
        user_client._headers["Authorization"] = "expired-token"  # noqa: SLF001

        response = user_client.post("conversation/chat/greeting", data=CHAT_DATA)

        assert response.status_code == 200
        assert [status for *_, status in recorder.calls] == [401, 200]
        assert recorder.calls[1][2]["Authorization"] != "expired-token"

    def test_logout_revokes_the_access_token(self, user_client: Client):
        recorder = ListRecorder()
        user_client.recorder = recorder
        user_client.post("conversation/chat/greeting", data=CHAT_DATA).raise_for_status()
        headers = recorder.calls[-1][2]

        user_client.logout(timeout=30)

        url = "https://%s/api/conversation/chat/greeting/" % user_client.host
        assert requests.post(url, headers=headers, json=CHAT_DATA, timeout=30).status_code == 401


class TestRestCalls:
    def test_generated_endpoint_fills_path(self, live_client: Client):
        dashboards = live_client.get("dashboard").json()
        if not dashboards:
            pytest.skip("no dashboard on this Kbot")
        cli: Any = live_client

        response = cli.get_dashboard(dashboards[0]["id"])

        assert response.status_code == 200
        assert response.json()["id"] == dashboards[0]["id"]

    def test_query_params_reach_the_server(self, live_client: Client):
        page = live_client.get("user", params={"num": 2}).json()

        assert page["size"] == 2
        assert len(page["users"]) <= 2

    def test_unit_returns_json_or_none(self, live_client: Client):
        assert isinstance(live_client.unit("dashboard"), list)
        assert live_client.unit("user/does-not-exist") is None

    def test_metric(self, live_client: Client):
        cli: Any = live_client

        response = cli.metric()

        assert response.status_code == 200
        assert response.json()["host"]["hostname"] == live_client.host

    def test_metric_filtered(self, live_client: Client):
        cli: Any = live_client

        response = cli.metric_filtered(metric_filter=[])

        assert response.status_code == 200


@pytest.mark.skipif(shutil.which("curl") is None, reason="curl is not installed")
def test_curl_printer_command_replays_with_curl(live_client: Client, capsys):
    live_client.recorder = CurlPrinter()

    response = live_client.get("user", params={"num": 1})

    command = shlex.split(capsys.readouterr().out)
    result = subprocess.run(
        [*command, "--silent", "--write-out", "\n%{http_code}"],
        capture_output=True, text=True, timeout=60, check=True,
    )
    body, status = result.stdout.rsplit("\n", 1)
    assert int(status) == response.status_code
    assert json.loads(body) == response.json()
