import time
import uuid
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from client import Client

JsonType = dict[str, "JsonType"] | list["JsonType"] | str | int | None


class ChatClient(ABC):  # noqa: D101
    def __init__(  # noqa: D107, PLR0913 ; pylint: disable=too-many-positional-arguments
        self,
        client: "Client",
        render_types: tuple[str, ...] = ("text", "html", "markdown"),
        prompt: str = "{sender}> {message}",
        user_prompt: str = "User> ",
        bye: str = "Bye, hope to see you again soon",
        assistant: str | None = None,
        exit_commands: tuple[str, ...] = ("stop", "exit"),
        convert_html_to_text: bool = False,
    ) -> None:
        self._client = client
        self._render_types = render_types
        self._prompt = prompt
        self._user_prompt = user_prompt
        self._bye = bye
        self._exit_commands = exit_commands
        self._assistant = assistant
        self._convert_html_to_text = convert_html_to_text

        # Create a new conversation
        #
        response = self._client.post(
            "conversation",
            data={
                "username": "bot",
                "assistant": assistant,
            },
        )
        response.raise_for_status()

        # Print the first welcome message
        #
        self._process_new_messages(response.json(), context="welcome")

        # Loop waiting for user questions and then waiting for the bot response
        #
        self._start_question_answer_loop(response.json().get("id"))

    def _process_new_messages(self,  # noqa: C901
                              messages_json: JsonType,
                              context: Literal["response", "welcome"]) -> bool:
        """Given a JSON response from the bot, extract two key information.

        Args:
            messages_json: A list of the JSON matching the type constraints such as:

        Arguments:
            context: One of "welcome" or "response"

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

        Returns:
            bool: ??? previous comment is invalid ???

        """
        stop = False
        if context == "welcome":
            self._sender = messages_json.get("sender").get("name")

            for message in messages_json.get("messages"):
                message_type = message.get("type")

                if message.get("type") != "message":
                    continue

                for message_content in message.get("message"):
                    if message_content.get("format") in self._render_types:
                        self._display_response(message_content)

        elif context == "response":

            stop = not messages_json.get("dialog_in_progress")

            for one_message in messages_json.get("messages"):

                message_type = one_message.get("type")

                if message_type == "typing":
                    continue

                self._sender = one_message.get("sender").get("name")

                if one_message.get("type") != "message":
                    continue

                for message_content in one_message.get("message"):
                    if message_content.get("format") in self._render_types:
                        self._display_response(message_content)

        return stop

    def _display_response(self, message: JsonType) -> None:
        """Display the message to the user.

        Args:
            message: The user message and the format in a dictionary.

        The message argument is a json in the format.
        {
            "format": "text",
            "value": "Hello John",
            ...
        }

        """
        # Potentially need to convert the message
        message_format = message.get("format")

        if message_format == "text":
            message_value = message.get("value")

        elif message_format == "html":
            if self._convert_html_to_text:
                try:
                    from bs4 import BeautifulSoup  # pylint: disable=import-error, import-outside-toplevel
                    message_value = BeautifulSoup(message.get("value"), "html.parser").get_text()
                except:  # noqa: E722
                    print(  # noqa: T201
                        "ERROR: HTML to Text conversion requested, but beautifull soup is not installed. Use: ",
                    )
                    print("pip3 install BeautifulSoup4")  # noqa: T201
                    message_value = message.get("value")
            else:
                message_value = message.get("value")
        elif message_format == "markdown":
            message_value = message.get("value")

        else:
            print("Unsupported format:", message.get("format"))  # noqa: T201
            message_value = message.get("value")

        # finally display the result to the user
        print(self._prompt.format(sender=self._sender, message=message_value))  # noqa: T201

    def _start_question_answer_loop(self, conversation_id: int) -> None:
        """Start the chatbot, in a loop.

        We stop when user type "exit" or EOF (Ctrl D).
        """
        while True:
            # Get the user sentence and check for the stop conditions
            #
            try:
                question = input(self._user_prompt)
            except EOFError:
                print(self._bye)  # noqa: T201
                break

            if not question:
                continue

            if question.lower() in self._exit_commands:
                print(self._bye)  # noqa: T201
                break

            self._send_question(question, conversation_id)
            self._get_response(conversation_id)

    def _send_question(self, question: str, conversation_id: int) -> None:
        # Send the user question to Kbot.
        #
        data = {
            "conversation_id": conversation_id,
            "type": "message",
            "message": question,
            "message_id": str(uuid.uuid4()),
            "assistant": self._assistant,
        }

        response = self._client.post(f"conversation/{conversation_id}/message", data=data)
        response.raise_for_status()

    @abstractmethod
    def _get_response(self, conversation_id: int) -> None:
        """Collect the kbot response."""


class AsyncChatClient(ChatClient):
    """A Chatbot client that will pull for updates and display responses as they come."""

    def __init__(self,  # noqa: D107
                 client: "Client",
                 pull_interval: float = 0.5,
                 pull_timeout: int = 10,
                 **kwargs: dict) -> None:
        self._pull_interval = pull_interval
        self._pull_timeout = pull_timeout
        super().__init__(client,**kwargs)

    def _get_response(self, conversation_id: int) -> None:
        # Wait for the response(s)
        #
        while True:
            time.sleep(self._pull_interval)
            response = self._client.get(
                f"conversation/{conversation_id}/messages",
                params={"timeout": self._pull_timeout},
            )
            response.raise_for_status()

            stop = self._process_new_messages(response.json(), context="response")
            if stop:
                # Time to ask for a new question
                break


class SyncChatClient(ChatClient):
    """A Chatbot client that will wait for full response from the bot before displaying to the user."""

    def _get_response(self, conversation_id: int) -> None:
        # Wait for the response(s)
        #
        params = {"wait": "true"}
        response = self._client.get(f"conversation/{conversation_id}/messages", params=params)
        response.raise_for_status()
        self._process_new_messages(response.json(), context="response")
