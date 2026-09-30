"""Shared fixtures: a fake Kbot server and clients connected to it."""

from collections.abc import Iterator

import pytest

from kbot_client import Client
from tests.fake_kbot import API_KEY, DEFAULT_SCHEMA, FakeKbot


@pytest.fixture
def kbot() -> Iterator[FakeKbot]:
    server = FakeKbot()
    server.route("GET", "/api/schema/", DEFAULT_SCHEMA)
    server.start()
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture
def client(kbot: FakeKbot) -> Client:
    """A client authenticated with an API key (fetches the schema on creation)."""
    return Client("127.0.0.1", port=kbot.port, api_key=API_KEY)


@pytest.fixture
def logged_in_client(kbot: FakeKbot) -> Client:
    """A client authenticated through ``login`` with access and refresh tokens."""
    kbot.route(
        "POST",
        "/api/login",
        {"access_token": "access-1", "refresh_token": "refresh-1", "user_id": "u-1"},
    )
    cli = Client("127.0.0.1", port=kbot.port)
    cli.login("alice", "secret")
    return cli
