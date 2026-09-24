from kbot_client import Client, chatbot_client

user_email = 'amedee.potier@konverso.ai'
user_firstname = "Amédée"
user_lastname = "Potier"
external_auth = "my-app"

# Create a session using an API key with strong privileges
cli = Client("my-kbot.konverso.ai", api_key="cb47-xxxxxxxxxxxxxxxxxxxxxxxxx")

response = cli.post("user/lookup_create", data={
    "user_name": user_email,
    "account_name": user_email,
    "account_type": "local",
    "external_auth": external_auth,
})
response.raise_for_status()

cli.impersonate(user_email, 'local', external_auth)

# Picks the chat client matching the Kbot version
chatbot_client.run(mode="synchronous", client=cli)
