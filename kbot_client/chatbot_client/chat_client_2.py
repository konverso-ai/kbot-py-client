__doc__ = """
A command line chatbot interface

Compatible with kbot version >= 2024.02

"""
import json
import sys
import uuid
import time
from abc import ABC, abstractmethod

class ChatClient(ABC):
    def __init__(self, client,
                 render_types=("text", "html", "markdown"),
                 prompt="{sender}> {message}",
                 type="chat",
                 user_prompt = "User> ",
                 bye = "Bye, hope to see you again soon",
                 assistant = None,
                 exit_commands = ("stop", "exit"),
                 display_intro=True,
                 convert_html_to_text=False,
                 show_streaming_parts=False):

        self._client = client
        self._render_types = render_types
        self._prompt = prompt
        self._user_prompt = user_prompt
        self._bye = bye
        self._exit_commands = exit_commands
        self._assistant = assistant
        self._convert_html_to_text = convert_html_to_text
        self._type = type
        self._conversation_id = None
        self._show_streaming_parts = show_streaming_parts

        data={
            "username": "bot",
            "type": type,
            "assistant_id": assistant
        }

        # Create a new conversation
        #
        response = self._client.post(f"conversation/{self._type}",
                                     data=data)
        response.raise_for_status()
        self._conversation_id = response.json().get("id")

        if display_intro:
            greeting_response = self._client.post(f"conversation/{self._type}/greeting",
                                                  data=data)
            greeting_response.raise_for_status()

            # Print the first welcome message
            #
            self._process_new_messages(greeting_response.json(), context="welcome")

        # Loop waiting for user questions and then waiting for the bot response
        #
        self._start_question_answer_loop()

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
        #print(messages_json)

        stop = False
        if context == "welcome":
            self._sender = messages_json.get("sender", {}).get("name", "")

            for message in messages_json.get("messages"):
                message_type = message.get("type")

                if message.get("type") != "message":
                    continue

                for message_content in message.get("parts"):
                    if message_content.get("format") in self._render_types:
                        self._display_response(message_content)

        elif context == "response":

            stop = not messages_json.get("dialog_in_progress")

            for one_message in messages_json.get("messages"):

                message_type = one_message.get("type")

                if message_type == "typing":
                    continue

                if message_type == "wait_user_input":
                    stop = True

                self._sender = one_message.get("sender").get("name")

                if one_message.get("type") != "message":
                    continue

                for message_content in one_message.get("parts"):
                    if message_content.get("format") in self._render_types:
                        self._display_response(message_content)

        return stop

    def _display_response(self, message):
        """Display to the user the message. The message argument is a json in the format:
            {
                      "format": "text",
                      "value": "Hello John",
                       ...
        """

        # Potentially need to convert the message: 
        message_format = message.get('format')

        if message_format == "text":
            message_value = message.get('value')

        elif message_format == "html":
            if self._convert_html_to_text:
                try:
                    from bs4 import BeautifulSoup
                    message_value = BeautifulSoup(message.get('value'), 'html.parser').get_text()
                except:
                    print("ERROR: HTML to Text conversion requested, but beautifull soup is not installed. Use: ")
                    print("pip3 install BeautifulSoup4")
                    message_value = message.get('value')
            else:
                message_value = message.get('value')
        elif message_format == "markdown":
            #print("Markdown part: %s", message)
            if not self._show_streaming_parts and message.get("mode") == "append":
                return
            message_value = message.get('value')

        else:
            print("Unsupported format:", message.get('format'))
            message_value = message.get('value')

        # finally display the result to the user
        print(self._prompt.format(sender=self._sender, message=message_value))

    def _start_question_answer_loop(self):

        # Start the chatbot, in a loop
        # We stop when user type "exit" or EOF (Ctrl D)
        while True:

            # Get the user sentence and check for the stop conditions
            #
            try:
                question = input(self._user_prompt)
            except EOFError:
                print(self._bye)
                break

            if not question:
                continue

            if question.lower() in self._exit_commands:
                print(self._bye)
                break

            self._send_question(question)
            self._get_response()


    def _send_question(self, question):
        # Send the user question to Kbot.
        #
        data = {
            'message_id': str(uuid.uuid4()),
            'type': 'message',
            'message': question,
            'status': 'sending',
            'fromUser': True,
        }
        response = self._client.post(f"conversation/{self._type}/{self._conversation_id}/message", data=data)
        response.raise_for_status()

    @abstractmethod
    def _get_response(self):
        """Collect the kbot response"""

class AsyncChatClient(ChatClient):
    """A Chatbot client that will pull for updates and display responses
       as they come
    """
    def __init__(self, client, pull_interval=0.5, pull_timeout=10, **kwargs):
        self._pull_interval = pull_interval
        self._pull_timeout = pull_timeout
        super().__init__(client,**kwargs)

    def _get_response(self):
        # Wait for the response(s)
        #
        while True:
            time.sleep(self._pull_interval)
            response = self._client.get(f"conversation/{self._type}/{self._conversation_id}/messages", params={"timeout": self._pull_timeout})
            response.raise_for_status()

            stop = self._process_new_messages(response.json(), context="response")
            if stop:
                # Time to ask for a new question
                break

class SyncChatClient(ChatClient):
    """A Chatbot client that will wait for full response from the bot before displaying to the user
    """

    def _get_response(self):
        # Wait for the response(s)
        #
        params = {"wait": "true"}
        response = self._client.get(f"conversation/{self._type}/{self._conversation_id}/messages", params=params)
        response.raise_for_status()
        self._process_new_messages(response.json(), context="response")


class WebSocketChatClient(ChatClient):
    """A Chatbot client that sends the user questions and receives the bot responses
       over the conversation web socket, displaying them as they come.

       The server closes the socket when a dialog turn ends, so the socket is
       (re)opened whenever a question needs to be sent.

       Streamed text parts arrive as "append" chunks sharing the same part id, often
       followed by a "replace" holding the full text. Chunks are buffered per part and
       displayed once the part is complete, unless show_streaming_parts is set.

       Requires the "websockets" package: pip install kbot-py-client[websocket]
    """
    def __init__(self, client, receive_timeout=120, **kwargs):
        try:
            # pylint: disable=import-outside-toplevel
            from websockets.sync.client import connect
            from websockets.exceptions import ConnectionClosed, InvalidStatus
        except ImportError as e:
            raise RuntimeError("The websocket mode requires the 'websockets' package. Use: "
                               "pip3 install 'kbot-py-client[websocket]'") from e

        self._connect = connect
        self._connection_closed = ConnectionClosed
        self._invalid_status = InvalidStatus
        self._receive_timeout = receive_timeout
        self._ws = None
        self._pending = {}    # part id -> (response id, sender, format, text so far)
        self._shown = {}      # part id -> text displayed
        self._streaming = None  # part id currently being streamed on screen
        self._streamed = ""     # text already streamed on screen for that part
        try:
            super().__init__(client, **kwargs)
        finally:
            self._close()

    @property
    def _socket_url(self):
        url = self._client.url
        if url.startswith("https://"):
            url = "wss://" + url[len("https://"):]
        elif url.startswith("http://"):
            url = "ws://" + url[len("http://"):]
        return f"{url}/api/conversation/{self._type}/{self._conversation_id}/ws/"

    def _open(self):
        """Opens the conversation socket. Returns True on success"""
        headers = {k: v for k, v in self._client.headers.items() if k.lower() != "content-type"}
        kwargs = {"additional_headers": headers}
        if self._socket_url.startswith("wss://") and not self._client.verify:
            # pylint: disable=import-outside-toplevel
            import ssl
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            kwargs["ssl"] = context
        try:
            self._ws = self._connect(self._socket_url, **kwargs)
        except self._invalid_status as e:
            print(f"ERROR: web socket refused: {e.response.status_code}")
            return False
        return True

    def _close(self):
        if self._ws is not None:
            try:
                self._ws.close()
            finally:
                self._ws = None

    def _send_question(self, question):
        frame = json.dumps({
            "type": "message",
            "message": question,
            "message_id": str(uuid.uuid4()),
        })
        # The server may close the socket between two turns: reopen once
        for _ in range(2):
            if self._ws is None and not self._open():
                return
            try:
                self._ws.send(frame)
                return
            except self._connection_closed:
                self._ws = None
        print("ERROR: could not send the question, the web socket keeps closing")

    def _get_response(self):
        """Reads frames until the bot hands the turn back to the user"""
        if self._ws is None:
            return
        try:
            while True:
                try:
                    raw = self._ws.recv(timeout=self._receive_timeout)
                except TimeoutError:
                    print(f"WARNING: no bot response received in {self._receive_timeout} seconds")
                    break
                try:
                    frame = json.loads(raw)
                except ValueError:
                    print("Unsupported (non JSON) frame:", raw)
                    continue
                if self._process_frame(frame):
                    break
        except self._connection_closed:
            # The server ends the socket once the dialog turn is over
            self._ws = None
        finally:
            self._flush()

    def _process_frame(self, frame):
        """Processes one socket frame. Returns True when the bot turn is over"""
        if frame.get("type") == "keepalive":
            return False

        stop = False
        for message in frame.get("messages", []):
            message_type = message.get("type")
            response_id = message.get("response_id")

            # A message from another response means the earlier ones are complete
            self._flush(keep=response_id)

            if message_type == "typing":
                continue

            if message_type == "wait_user_input":
                stop = True
                continue

            if message_type not in ("message", "notification"):
                continue

            sender = message.get("sender", {}).get("name", "")
            for part in message.get("parts", []):
                self._process_part(response_id, sender, part)

        if frame.get("dialog_in_progress") is False:
            stop = True
        return stop

    def _process_part(self, response_id, sender, part):
        part_format, part_id = part.get("format"), part.get("id")
        if part_format not in self._render_types:
            return
        value = part.get("value") or ""

        # html parts come whole, and replace parts hold the full text
        if part.get("mode") == "replace" or part_format == "html":
            self._pending.pop(part_id, None)
            self._show(part_id, sender, part_format, value)
            return

        _, _, _, so_far = self._pending.get(part_id, (response_id, sender, part_format, ""))
        self._pending[part_id] = (response_id, sender, part_format, so_far + value)

        if self._show_streaming_parts:
            if self._streaming != part_id:
                self._end_streaming()
                self._streaming = part_id
                self._streamed = ""
                sys.stdout.write(self._prompt.format(sender=sender, message=""))
            sys.stdout.write(value)
            sys.stdout.flush()
            self._streamed += value

    def _end_streaming(self):
        if self._streaming is not None:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._shown[self._streaming] = self._streamed.strip()
            self._streaming = None
            self._streamed = ""

    def _flush(self, keep=None):
        """Displays every buffered part, except those of the response 'keep' which may still be streaming"""
        for part_id, (response_id, sender, part_format, text) in list(self._pending.items()):
            if response_id != keep:
                if part_id == self._streaming:
                    self._end_streaming()
                del self._pending[part_id]
                self._show(part_id, sender, part_format, text)

    def _show(self, part_id, sender, part_format, text):
        text = text.strip()
        if not text or self._shown.get(part_id) == text:
            return
        if part_id == self._streaming:
            self._end_streaming()
            if self._shown.get(part_id) == text:
                return
        self._shown[part_id] = text
        self._sender = sender
        self._display_response({"format": part_format, "value": text, "mode": "replace"})
