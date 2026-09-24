"""Tests for kbot_client.client_group.ClientGroup."""

import pytest

from kbot_client import Client, ClientGroup, DownKbotClient, UpKbotClient


def test_append_accepts_clients_and_subclasses():
    group = ClientGroup()
    clients = [Client("a.example"), UpKbotClient("b.example"), DownKbotClient("c.example", error="down")]

    for cli in clients:
        group.append(cli)

    assert list(group) == clients


@pytest.mark.parametrize("value", ["a.example", None, object()])
def test_append_rejects_non_clients(value):
    group = ClientGroup()

    with pytest.raises(AssertionError):
        group.append(value)

    assert len(group) == 0
