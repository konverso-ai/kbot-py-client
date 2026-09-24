"""Fixtures for live tests against a real Kbot instance.

Live tests are skipped unless these environment variables are set (never commit
credentials):

- ``KBOT_LIVE_HOST``: Kbot host, e.g. ``vm-qa202601dev-we-d.konverso.ai``
- ``KBOT_LIVE_API_KEY``: API key allowed to create and impersonate users
- ``KBOT_LIVE_FOLDER_UUID``: File Manager folder in which file tests create,
  then remove, a sandbox sub folder (file tests are skipped without it)
"""

import os
import time
import uuid
from collections.abc import Iterator

import pytest

import kbot_client.client
from kbot_client import Client
from tests.live.helpers import TEST_EXTERNAL_AUTH, TEST_USER

def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip("%s is not set" % name)
    return value


@pytest.fixture(scope="session")
def live_host() -> str:
    return _env("KBOT_LIVE_HOST")


@pytest.fixture(scope="session")
def live_api_key() -> str:
    return _env("KBOT_LIVE_API_KEY")


@pytest.fixture
def live_client(live_host: str, live_api_key: str) -> Client:
    """A client authenticated with the API key."""
    return Client(live_host, api_key=live_api_key)


@pytest.fixture
def user_client(live_client: Client) -> Client:
    """A client impersonating the dedicated test end user."""
    response = live_client.post(
        "user/lookup_create",
        data={
            "user_name": TEST_USER,
            "account_name": TEST_USER,
            "account_type": "local",
            "external_auth": TEST_EXTERNAL_AUTH,
        },
    )
    response.raise_for_status()
    live_client.impersonate(TEST_USER, "local", TEST_EXTERNAL_AUTH)
    return live_client


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip the client's 3 s back-off between token refresh attempts."""
    monkeypatch.setattr(kbot_client.client.time, "sleep", lambda _seconds: None)


def _delete_folder(cli: Client, folder: str) -> None:
    listing = cli.request("get", uri="folder/%s/list" % folder)
    listing.raise_for_status()
    for sub_folder in listing.json().get("folders", []):
        _delete_folder(cli, sub_folder["uuid"])
    for remote_file in listing.json().get("files", []):
        cli.delete("attachment/%s" % remote_file["uuid"]).raise_for_status()
    cli.delete("folder/%s" % folder).raise_for_status()


@pytest.fixture
def sandbox_folder(live_host: str, live_api_key: str) -> Iterator[str]:
    """A fresh File Manager folder, removed with its content afterwards."""
    parent = _env("KBOT_LIVE_FOLDER_UUID")
    cli = Client(live_host, api_key=live_api_key)
    name = "kbot-py-client-tests-%s-%s" % (time.strftime("%Y%m%d-%H%M%S"), uuid.uuid4().hex[:6])
    response = cli.request("post", uri="folder", data={"name": name, "parent": parent})
    response.raise_for_status()
    folder = response.json()["uuid"]
    try:
        yield folder
    finally:
        _delete_folder(cli, folder)
