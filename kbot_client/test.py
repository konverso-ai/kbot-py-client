import json

from kbot_client import Client

# Option 1: using an API Key
client = Client("myhost.konverso.ai", api_key="18460555-9012-4a43-bf68-fc55325b96af")

# Option 2: using a user login
client = Client("myhost.konverso.ai")
client.login("myuser", "mypassword")

metrics = client.metric()
print(f"Collected metrics ({metrics}):")       # noqa: T201
print(metrics.text)                            # noqa: T201
print(json.dumps(metrics.json(), indent=4))    # noqa: T201

r = client.conversation(username="bot")
print(f"Post conversation ({r}):")             # noqa: T201
print(r.text)                                  # noqa: T201

r = client.get_dashboard(1)
print(f"Get dashboard ({r}):")                 # noqa: T201
print(r.text)                                  # noqa: T201

client.logout()
