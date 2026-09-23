"""Recorders used to trace the API activity of a Client"""
import json
import shlex


class Recorder:
    """Base class for recording the API calls made by a Client.

    Subclasses should override `record`, which is invoked once per HTTP
    call performed by `Client.__request`, after the response has been
    received.
    """

    def record(self, method: str, url: str, headers: dict = None, data=None, files: dict = None, response=None):
        """Called after each API request is made.

        Arguments:
            - method: the HTTP method, such as "GET" or "POST"
            - url: the full URL that was called, including query string
            - headers: the headers sent with the request
            - data: the request payload, as passed to the client (before serialization)
            - files: the files sent with the request, if any
            - response: the requests.Response object returned by the call
        """
        raise NotImplementedError


class Printer(Recorder):
    """Recorder that prints the URL, protocol, payload and response of each API call"""

    def record(self, method: str, url: str, headers: dict = None, data=None, files: dict = None, response=None):
        proto = url.split(':', 1)[0]
        print("%s %s (%s)" % (method.upper(), url, proto))
        if headers:
            print("  headers: %s" % headers)
        if data:
            print("  payload: %s" % data)
        if files:
            print("  files: %s" % list(files.keys()))
        if response is not None:
            print("  -> %s %s" % (response.status_code, response.text))


class CurlPrinter(Recorder):
    """Recorder that prints the equivalent curl command of each API call"""

    def record(self, method: str, url: str, headers: dict = None, data=None, files: dict = None, response=None):
        print(self.to_curl(method, url, headers=headers, data=data, files=files))

    @staticmethod
    def to_curl(method: str, url: str, headers: dict = None, data=None, files: dict = None) -> str:
        """Builds the curl command line equivalent to the given request"""
        parts = ["curl", "-X", method.upper()]

        for name, value in (headers or {}).items():
            parts.append("-H %s" % shlex.quote("%s: %s" % (name, value)))

        if files:
            for name in files:
                parts.append("-F %s" % shlex.quote("%s=@<file>" % name))
            for name, value in (data or {}).items():
                parts.append("-F %s" % shlex.quote("%s=%s" % (name, value)))
        elif data:
            body = data if isinstance(data, str) else json.dumps(data)
            parts.append("-d %s" % shlex.quote(body))

        parts.append(shlex.quote(url))

        return " ".join(parts)
