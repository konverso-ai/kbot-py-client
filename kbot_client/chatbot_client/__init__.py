# Client for Kbot version up to 2024.01
from . import chat_client

# Client for Kbot version from 2024.02
from . import chat_client_2

def _get_module(version):
    """Returns the proper ChatClient module for the given version"""
    if not version:
        return chat_client

    if version <= "2024.01":
        return chat_client

    return chat_client_2

def _get_chatbot_instance(version, class_name, **kwargs):
    """Create a ChatClient instance for the given version and type"""
    module = _get_module(version)
    cls = getattr(module, class_name)
    return cls(**kwargs)

def run(mode="synchronous", **kwargs):
    """Starts an interactive ChatClient for the given client, in the selected mode

    Arguments:
        - mode: One of "synchronous" or "asynchronous"
    """

    client = kwargs.get("client")
    if not client:
        raise RuntimeError("Missing mandatory 'client' parameter")

    version = client.version

    if mode == "asynchronous":
        return _get_chatbot_instance(version, "AsyncChatClient", **kwargs)

    return _get_chatbot_instance(version, "SyncChatClient", **kwargs)
