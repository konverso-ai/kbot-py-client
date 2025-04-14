__doc__ = """

A utility class you may use to wrap a given Client, providing the user identity and connectivity to a bot
with a set of interaction. 

This class will create a Conversation in the remote bot, and then you can push new message to it using the "send" method. 

The callback will be called whenever a new response comes in, with the message response payload.

Here is a sample callback you may use, that would 'print' the responses:

    def response_received_callback(js):
        for message in js.get("messages", []):
            mtype = message.get("type")
            if mtype == "message":
                # A message to be displayed to the user
            else:
                # A system message (extra information

        if js.get("dialog_in_progress") is False:
            # We are at the end of the remote bot response.
            # We need to notify our dialog such that it allows for new user input
            log.debug("Response completed")
            print("Response is now complete")
            # You may let the user enter new question

If using this module directly inside Kbot to delegate the processing to remote bots,
please check also the kbot utility module: wf/remote_dialog.py that will map a Dialog instance
with this AsyncCallbackChatClient

The overall flow of a conversation is: 
    - create()
    - loop of:
       - attach() (Optional)
       - send()
       - get_response()
    - close()  (Optional, will otherwise close with a timeout)
    - delete() (Optional)
"""
import uuid
import time

class AsyncCallbackChatClient:
    #pylint: disable=redefined-builtin
    #pylint: disable=too-many-positional-arguments
    def __init__(self, client, type,
                 assistant = None,
                 exit_commands = ("stop", "exit"),
                 callback=None,
                 pull_interval=0.5,
                 pull_timeout=10,
                 display_intro=True,
                 **kwargs):
        """
        Arguments:
            - client: A Client instance
            - type: One of "chat" or "agentic"
            - callback: Option function that will be called on each response
                        If defined, then the interactive "prompt" is not used
        """

        self._client = client
        self._exit_commands = exit_commands
        self._assistant = assistant
        self._pull_interval = pull_interval
        self._pull_timeout = pull_timeout
        self._callback = callback
        self._type = type

        data={
            "username": "bot",
            "type": type,
            "assistant_id": assistant
        }
        if display_intro:
            greeting_response = self._client.post(f"conversation/{self._type}/greeting", data=data)
            greeting_response.raise_for_status()

        # then create a new conversation
        #
        response = self._client.post(f"conversation/{self._type}", data=data)
        response.raise_for_status()

        messages_json = response.json()

        self._conversation_uuid = messages_json.get("id")

        if display_intro:
            self._callback(greeting_response.json())

    @property
    def conversation_uuid(self):
        return self._conversation_uuid

    @property
    def client(self):
        return self._client

    def _process_new_messages(self, messages_json, context):
        """Given a JSON response from the bot, extract two key information:
           - sender: The name of the bot
           - messages: A list of the JSON matching the type constraints such as:

          Arguments:
           - context: One of "welcome" or "response"

           The input json of a Welcome (conversation creation) is expected to have format such as:
           {
               "sender": {...}
               "messages": [{
                    "type": "message",
                    "message": [{
                         "format": "text",
                         "value": "Hello John",
                          ...

           The input json of a Response (conversation response) is expected to have format such as:
           [{
                "sender": {...}
                 "type": "message",
                 "message": [{
                      "format": "text",
                      "value": "Hello John",
                       ...

           Returns a tuple of two elements: sender, messages
        """
        stop = not messages_json.get("dialog_in_progress")
        self._callback(messages_json)
        return stop

    def send(self, question):
        """Send the user question to Kbot.

           Args:
               question (str): some user message
        """
        data = {
            'message_id': str(uuid.uuid4()),
            'type': 'message',
            'message': question,
            'status': 'sending',
            'fromUser': True,
        }

        response = self._client.post(f"conversation/{self._type}/{self._conversation_uuid}/message", data=data)
        response.raise_for_status()

    def attach(self, file_name, file_path):
        """Send the given file to Kbot.

           Args:
               file_name (str): The real file name (e.g. "Daily Status.doc")
               file_path (str): The complete file path (e.g. "/tmp/my_status.doc")               
        """
        data = {
            'message': file_name,
            'type': 'attachment',
        }

        with open(file_path, "rb") as fd:
            response = self._client.post_file(f"conversation/{self._type}/{self._conversation_uuid}/message",
                    data=data,
                    files = {"file": (file_name, fd)})
        response.raise_for_status()

    def get_response(self):
        """Collect the kbot response and call the callback for each received response"""
        # Wait for the response(s)
        #
        while True:
            time.sleep(self._pull_interval)
            response = self._client.get(f"conversation/{self._type}/{self._conversation_uuid}/messages", params={"timeout": self._pull_timeout})
            response.raise_for_status()

            stop = self._process_new_messages(response.json(), context="response")
            if stop:
                # Time to ask for a new question
                break

    def close(self):
        response = self._client.post(f"conversation/{self._type}/{self._conversation_uuid}/close")
        response.raise_for_status()

    def delete(self):
        response = self._client.delete(f"conversation/{self._type}/{self._conversation_uuid}")
        response.raise_for_status()
