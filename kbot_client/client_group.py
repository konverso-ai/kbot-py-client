"""Client for Open Chat Bot.

A client group is a list of clients. This may be used to send a given
user query to a number of bots and retrieve all results, typically
to get the higher rank answer, or to compare the various performances, etc.

Authors:
    - Amédée Potier (amedee.potier@konverso.ai) from Konverso

History:
    - 2020/11/02: Amédée: Initial class implementation
"""

from kbot_client.client import Client


class ClientGroup(list):  # noqa: D101
    def append(self, client: Client) -> None:  # noqa: D102
        assert isinstance(client, Client)
        super().append(client)
