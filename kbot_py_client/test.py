
import json

from kbot_client import Client

# Option 1: using an API Key
client = Client("myhost.konverso.ai", api_key="18460555-9012-4a43-bf68-fc55325b96af")

# Option 2: using a user login
client = Client("myhost.konverso.ai")
client.login("myuser", "mypassword")

metrics = client.metric()
print("Collected metrics (%s):" % (metrics))
print(metrics.text)
print(json.dumps(metrics.json(), indent=4))

r = client.conversation(username='bot')
print("Post conversation (%s):" % (r))
print(r.text)

r = client.get_dashboard(1)
print("Get dashboard (%s):" % (r))
print(r.text)

client.logout()
