# kbot-py-client #
This package contains utilities which you may use to easily interact with Konverso Kbot application.

In particular, you may:

* Invoke some of the APIs to view / update / create Kbot configuration objects such as Intents, Message, etc.
* Collect metrics showing how the bot is performing.
* Create a Conversation and interact with it, sending message and getting responses

# See also #

## Access Konverso Support
You may contact us:

* For any commercial inquiry: contact@konverso.ai
* For support: https://konverso.atlassian.net/servicedesk/customer/portals

## License
This client code is open source such that you can freely view it, modify it, create your own version.
We of course appreciate any contribution and sharing of enhancements made.

# Installation #

You may use pip3 to install the software on your Kbot instance:

`pip3 install kbot-py-client`

Alternatively, you can invoke a more explicity pip installation request, with the URL path:

`pip3 install -e git+https://github.com/konverso-ai/kbot-py-client.git#egg=kbot-py-client`

# Usage #

You would typically first need to login and then invoke some of the API wrapped methods.

## Login ##
```python
import json

from kbot_client import Client
```
### Using user / password ###
```python
cli = Client("mybot.konverso.ai")
cli.login("myuser", "mysecretpassword")
```

The API Key may be created for a given user, with relevant permissions, from the Configuration / Users & Roles / Users / Accounts panel. Create an account of type "Local"

### Using and api key ###
```python
cli = Client("mybot.konverso.ai", api_key="xxxxxxxxxxxxxxxxxxx")
```
The API Key may be created for a given user, with relevant permissions, from the Configuration / Users & Roles / Users / Accounts panel. Create an account of type "API Key"

### User impersonation
If you have an API key created with sufficient permissions, then you can use the client impersonation.
```python
cli = Client("mybot.konverso.ai", api_key="xxxxxxxxxxxxxxxxxxx")
cli.impersonate(user_name, 'local', external_auth='')
```
The above will generate a client for the user 'user_name'. This user must exists. If you are in an integration where you need to create the user, then we suggest to add a call first to the lookup/create before. 
```python
```

The API Key may be created for a given user, with relevant permissions, from the Configuration / Users & Roles / Users / Accounts panel. Create an account of type "API Key"

## Collect metrics
Once authenticated, you can for example retrieve useful usage metrics, these can be used by a Monitoring application or for some business intelligence rendering:
```python
metrics = cli.metric().json()
print("Collected metrics:")
print(json.dumps(metrics, indent=4))
```

## Invoke a Workflow and retrieve result
This is the most powerful mechanism, that let you invoke any business and processing logic in a workflow, leveraging all the capabilities of our platform, and retrieve the result:

```python
r = client.request("post",
    "workflow/execute",
    {
        "name": "Test API Workflow",
        "keywords": {
            "var1": "abc"
        },
        "result": ["response"]
    }
)
print(r.json())
```

## Invoke a search
You may invoke a search on any of the configured Search Contexts
Note the search context UUID passed in the URL, which you may retrieve from our Search Context portal.

```python
r = client.request("post", "searchcontext/234923-235-sjdhfs-kdjf/search",
    {
        "sentence": "how to create a classifier",
        "num_results": 20,
        #"variables": {'kbs': {'value': ['Confluence_Security_KSEC']}}
    }
)
```

## Get list of objects and check if object with name is present in response
You may retrieve list of defined objects. Note that only objects visibled to the logged in users will be returned.

Here is a sample code that simply checks for a few objects existance:

```python
for unit, name in (('intention' ,'Create ticket'),
                    ('knowledge_base', 'faq'),
                    ('workflow', 'Transfer to Agent')):
    print(f"Get list of '{unit}'")
    objs = cli.unit(unit)
    if objs:
        # Create dict with
        # - key : object name
        # - value : object json data
        data = {obj['name']: obj for obj in objs}
        if name in data:
            print(f"'{name}' is present")
        else:
            print(f"'{name}' is not present")
    else:
        print("Get no data")
```

## Conversation test
In this example, we create a conversation between the logged in user and the bot and then sends a sentence, and check if we get some expected text in the response. This could for example be the basis of automated testing of the bot
```python
r = cli.conversation(username='bot')
if r.status_code == 201:
    cid = r.json().get('id')
    print("Created conversation with id '%s'" %(cid,))

    response = cli.message(cid, 'hello')

    # Process bot response
    if response:
        for resp in response:
            for message in resp.get('message', []):
                responses.append(message.get('value', '')) # dict {message type: message value}
                resp_message = '\n'.join(responses)
                print("Received response: ", resp_message)
                if 'I am kbot' in resp_message:
                    print("Excepted response found")
                    break
            else:
                print("Did not receive the expected response")
    else:
        print("Did not receive any response")
else:
    print("Could not create conversation due to: ", r.text)
```

## User creation and impersonation
The following sample is a complete example you may use to kick off a chat for a given user with the kbot chatbot.
Here there is no user authentication, but impersonation instead, and user/lookup. This example is a good starting point if you are looking at implementing your own chat interface on top of Kbot.
```python
# Create a session using an API key with strong privileges
cli = Client("mytenant.konverso.ai", api_key="34exxxxxxxxxxxxxa7bfb6aeb")

# Lookup create the user in kbot

response = cli.post("user/lookup_create", data={
    "user_name": user_email,
    "account_name": user_email,
    "account_type": "local",
    "external_auth": "nice-in-connect",
})
response.raise_for_status()

cli.impersonate(user_email, 'local', 'nice-in-connect') #, application_uuid="b0d91200-833f-466c-b5fd-1b0402cc3a36")
# Start the client (loop… ends with Ctrl D)
AsyncChatClient(cli)
```

## Uploading one file to kbot

### Prerequisites
* A local file that you wish to send
* The UUID of the folder that will receive the files you want to upload

### Code sample
```python
current_top_folder = "uuid-of-a-folder"
filepath = "/tmp/test.pdf"
filename = os.path.basename(filepath)

# Upload to remote filemanager
with open(filepath, "rb") as fd:
    files = {
                "upload_files": fd
            }
    params= {
                "override": False
            }
    data = {
                "folder": current_top_folder,
                "name": file_name,
            }
    response = self.client.post_file("attachment",
```

## Uploading a batch of files to the file manager

### Prerequisites

* An API key
* The UUID of the folder that will receive the files you want to upload

### Code sample
In this example, we simply upload the content of a directory to a folder in the file manager.
```python
from kbot_client import Client
from kbot_client.folder_sync import FolderSync

client = Client("mybot.konverso.ai", api_key="17ebXXXXXXXXXXXXXXXXXXXXX")

syncer = FolderSync(client)
syncer.sync("/tmp/my_source_folder/", "1831f-XXXXXXXXXXXXXXXXXXXXXXX")
print("Syncing is done :)")
````

## A command line chatbot
We provide a sample command line chatbot, available in Sync or Async mode

In this example, we simply initialize a chatbot client after creating a relevant User and Impersonating to it.
This is a good example of implementation of a custom Client for the Kbot product.

```python
# Create your client
import json
from kbot_client import Client
from kbot_client import chatbot_client

cli = Client("mytenant.konverso.ai", api_key="mykey")

external_auth = "cmd-line-chatbot"
user_email = "a-user-name"
assistant = "225d9647-0b41-473d-b097-ef4be363958a"

# Create your target user
response = cli.post("user/lookup_create", data={
    "user_name": user_email,
    "account_name": user_email,
    "account_type": "local",
    "external_auth": external_auth,
})
response.raise_for_status()

# Impersonate accordingly
cli.impersonate(user_email, 'local', external_auth)

# Start the chat
chatbot_client.run(client=cli, assistant=assistant, convert_html_to_text=True, mode="asynchronous")
```
Note that the above example is using a asynchronous call, meaning the client will listen for bot messages
in a loop and publish the messages as they are received

For a simple chatbot, you do not need to provide the 'assistant' parameter.

Alternatively, you can also use our synchronous client. This will listen for messages and only return once
all the messages are received for the user question.

```python
from kbot_client import chatbot_client
...
chatbot_client.run(mode="synchronous", client=cli, assistant=assistant, convert_html_to_text=True)
```
