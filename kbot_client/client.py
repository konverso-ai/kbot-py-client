"""Dialog tester."""
import json
import time

import requests

from kbot_client.chat_client import JsonType


class Client:
    """Base representation of Kbot instance."""

    def __init__(  # pylint: disable=too-many-positional-arguments
        self,
        server: str,
        port: int = 443,
        proto: str = "https",
        api_key: str | None = None,
        verify: bool = True,
    ) -> None:
        """Get the base configuration for our Client.

        Arguments:
            server (str): an Host or Ip Address
            port (int): default to 443
            proto (str): HTTP or HTTPS
            api_key (str): A Kbot valid API Key. If provided all requests will be sent with this API Key
                           and it is not required to invoke the login method
            verify (bool): Verify if certificates are valid

        """
        self.host = server
        self.verify = verify

        proto = "https" if str(port).endswith("443") else "http"

        if port in (80, 443):
            self.url = f"{proto}://{server}"
        else:
            self.url = f"{proto}://{server}:{port}"

        self._login = False
        self._headers = {}

        # The refresh token may be used in case
        # the access token as expired
        self.__refresh_token = None

        if api_key:
            self._headers = {
                "Content-Type": "application/json; charset=utf-8",
                "X-API-KEY": api_key,
            }
            self.schema()

        # Variable populated by the login:
        self._user_id = None

        # Variable populated by the conversation
        self._cid = None

    @property
    def admin_url(self) -> str:
        """Returns the URL of the Kbot Administration view."""
        return f"{self.url}/admin"

    @property
    def chat_url(self) -> str:
        """Returns the default URL of the Kbot chat view."""
        return f"{self.url}"

    @property
    def avatar_url(self) -> str:  # noqa: D102
        return f"{self.url}/images/kbot_avatar.png"

    def login(self, username: str, password: str | None = None, timeout: int = 5) -> None:
        """Login to local channel."""
        data = {}
        data["username"] = username
        data["usertype"] = "local"
        if password is not None:
            data["password"] = password
        else:
            print("WARNING!!! Password is not set!!! Trying to use username...")  # noqa: T201
            data["password"] = username

        headers = {}
        headers["Content-Type"] = "application/json; charset=utf-8"

        url = self.url + "/api/login"
        r = requests.post(url, headers=headers, data=json.dumps(data), timeout=timeout, verify=self.verify)

        r.raise_for_status()

        self.__reset_headers(r.json())
        self.schema()

    def impersonate(self,  # pylint: disable=too-many-positional-arguments
                    username: str,
                    usertype: str = "local",
                    external_auth: str = "",
                    userdata: dict | None = None,
                    timeout: int = 5) -> None:
        """Impersonate the given user."""
        r = self.request("post", "user/impersonate", data={
            "username": username,
            "im_type": usertype,
            "external_auth": external_auth,
            "userdata": userdata or {}})

        r.raise_for_status()

        self.__reset_headers(r.json())
        # After we impersonnate, we need to remove the original API KEY
        if "X-API-KEY" in self._headers:
            del self._headers["X-API-KEY"]

        self.schema()

    def schema(self) -> None:
        """Retrieve the public schema of kbot and builds python method for each of the defined end points."""
        r = self.get("schema")
        r.raise_for_status()

        j = r.json()
        for epoint in j.get("endpoints", []):
            if epoint["name"] != "schema":
                self.__add_method(
                    epoint["method"],
                    epoint["name"],
                    epoint["path"],
                    epoint["params"],
                    epoint["data"],
                    epoint.get("description", ""),
                )

    def __reset_headers(self, js: JsonType) -> None:
        """Reset headers due to login or impersonate.

        Args:
            js (JsonType): Json with access token and refresh token (optional)

        In the case of a refresh call, we only get only the access token.

        The header content is ajusted with the token information from the json.

        """
        if not self._headers:
            self._headers = {}
            self._headers["Content-Type"] = "application/json; charset=utf-8"

        if js.get("access_token"):
            self._headers["Authorization"] = js["access_token"]

        # The refresh token will be used by the refresh_token method later if the access token expires
        if js.get("refresh_token"):
            self.__refresh_token = js["refresh_token"]

        self._login = True
        if js.get("user_id"):
            self._user_id = js["user_id"]

    def __add_method(self,  # noqa: PLR0913 ; pylint: disable=too-many-positional-arguments
                     method: str,
                     name: str,
                     path: str,
                     params: list,
                     data: list,
                     description: str) -> None:
        """Add a new dynamic method, based on the schema.

        This provides "python method" wrapper on top of the kbot APIs.

        """
        def endpoint(*args, **kwargs) -> requests.Response:
            """Invoke request to endpoint."""
            rargs = {}
            for aname, values in (("params", params), ("data", data)):
                rargs[aname] = {}
                for value in values:
                    if value["mandatory"] and value["name"] not in kwargs:
                        msg = f"Missed attribute '{value["name"]}' in '{aname}'"
                        raise RuntimeError(msg)
                    # pylint: disable=eval-used
                    if value["name"] in kwargs:
                        if not isinstance(kwargs[value["name"]], eval(value["type"])):  # noqa: S307
                            msg = f"Invalid type of attribute '{value['name']}'"
                            raise RuntimeError(msg)
                        v = kwargs[value["name"]]
                    elif value["name"] not in kwargs and value["default"] is not None:
                        v = value["default"]
                    else:
                        continue
                    rargs[aname][value["name"]] = v
            return self.__request(method, uri=path % args, **rargs)
        endpoint.__doc__ = description
        endpoint.__name__ = name
        setattr(self, name, endpoint)

    def __refresh(self) -> None:
        r = requests.post(
            self.url + "/api/refresh",
            data=json.dumps({"refresh_token": self.__refresh_token}),
            headers=self._headers,
            timeout=5,
        )
        r.raise_for_status()
        self.__reset_headers(r.json())

    def __request(  # noqa: PLR0913 ; pylint: disable=too-many-positional-arguments
        self, method: str,
        uri : str | None = None,
        data: JsonType = None,
        params: JsonType = None,
        files: dict | None = None,
        attempt: int = 0,
    ) -> requests.Response:
        dump_data = data or json.dumps(data or {})

        if files:
            headers = self._headers.copy()
            del headers["Content-Type"]
            headers["Accept"] = "*/*"
        else:
            headers = self._headers

        r = requests.request(
            method.upper(),
            self.url + f"/api/{uri}/",
            params=params,
            data=dump_data,
            headers=headers,
            files=files,
            verify=self.verify,
            timeout=5,
        )

        if r.status_code == 401:  # noqa: PLR2004
            # Refresh the token
            try:
                self.__refresh()
            except Exception:

                # We try 3 times at the most
                if attempt == 3:  # noqa: PLR2004
                    raise

                time.sleep(3)

            # Re-invoke the request
            r = self.__request(method, uri=uri, data=data, params=params, attempt=attempt+1)

        return r

    def request(  # noqa: D102 ; pylint: disable=too-many-positional-arguments
        self,
        method: str,
        uri: str,
        data: dict | None = None,
        params: dict | None = None,
        files: dict | None = None,
    ) -> requests.Response:
        return self.__request(method, uri=uri, data=data, params=params, files=files)

    def unit(self, name: str, params: dict | None = None) -> dict:  # noqa: D102
        r = self.get(name, params)
        if not r:
            return None

        return r.json()

    def message(self, cid: int, message: str, timeout: int = 60) -> list:  # noqa: D102
        response = []

        data = {
            "type": "message",
            "message": message,
        }
        r = self.request("post", f"conversation/{cid}/message", data)

        r.raise_for_status()

        curtime = time.time()
        while timeout > 0:
            r = self.get(f"conversation/{cid}")

            r.raise_for_status()

            j = r.json()
            for resp in j:
                if resp["type"] == "message":
                    # It's possible that bot will send several message to one input
                    response.append(resp)
                elif resp["type"] in ("stop_topic", "wait_user_input"):
                    # Bot stop to process
                    # - stop_topic : bot stop to process message and ready for new topic
                    # - wait_user_input : bot asked the question and wait for user answer
                    timeout = 0
            timeout = timeout + curtime - time.time()
        return response

    def logout(self) -> None:
        """Logout from local channel."""
        if self._login:
            # If we have an open conversation, close it.
            # if self._cid:
            # What for?
            # self._process('logout', 1)  # noqa: ERA001

            # Logout from the APIs
            requests.post(self.url + "/api/logout", headers=self._headers, verify=self.verify, timeout=5)

    #
    # In addition to the Generated and built in API methods, we have the classic base REST methods
    #
    def get(self, unit: str, params: JsonType = None) -> requests.Response:  # noqa: D102
        return self.__request("get", unit, params=params)

    def put(self, unit: str, data: JsonType = None) -> requests.Response:  # noqa: D102
        return self.__request("put", unit, data=data)

    def post(self, unit: str, data: JsonType = None) -> requests.Response:  # noqa: D102
        return self.__request("post", unit, data=data)

    def delete(self, unit: str, params: JsonType = None) -> requests.Response:  # noqa: D102
        return self.__request("delete", unit, params=params)

    def post_file(
        self, unit: str,
        data: JsonType,
        params: JsonType = None,
        files: list[str] | None = None,
    ) -> requests.Response:
        """Attach the given files.

        Sample parameter values:
            unit = "attachment"
            files = {
                "upload_files": (f, fd, "application/pdf")
            }
            params= {
                "override": False
            }
            data = {
                "folder": current_top_folder,
                "name": f,
            }

        """
        return self.__request("post", unit, params=params, data=data, files=files)

class UpKbotClient(Client):
    """Represents a currently reachable Kbot instance."""


class DownKbotClient(Client):
    """Represents a currently not reachable Kbot instance."""

    def __init__(self, server: str, port: int = 443, proto: str="http", error: str = "") -> None:  # noqa: D107
        super().__init__(server, port=port, proto=proto)
        self.error = error
