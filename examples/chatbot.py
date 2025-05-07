from kbot_client import Client  # noqa: INP001
from kbot_client.chat_client import SyncChatClient

user_email = "amedee.potier@konverso.ai"
user_firstname = "Amédée"
user_lastname = "Potier"

# Create a session using an API key with strong privileges
cli = Client("my-kbot.konverso.ai", api_key="cb47-xxxxxxxxxxxxxxxxxxxxxxxxx")

response = cli.post("user/lookup_create", data={
    "user_name": user_email,
    "account_name": user_email,
    "account_type": "local",
    "external_auth": "my-app",
})
response.raise_for_status()

cli.impersonate(user_email, "local", "nice-in-connect", application_uuid="b0d91200-833f-466c-b5fd-1b0402cc3a36")  # pylint: disable=unexpected-keyword-arg

SyncChatClient(cli)
