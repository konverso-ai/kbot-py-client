"""Dialog tester"""
import json
import time

import requests


class Client:
    """Base representation of Kbot instance"""

    def __init__(self, server, port=443, proto='https', api_key=None, verify=True):
        """


        Arguments:
            - server: an Host or Ip Address
            - port : default to 443
            - proto: HTTP or HTTPS
            - api_key: A Kbot valid API Key. If provided all requests will be sent with this API Key
                       and it is not required to invoke the login method
        """

        self.host = server
        self.verify = verify

        # A version, in the formation "YEAR-V", such as 2024.02
        self.version = None

        if str(port).endswith('443'):
            proto = 'https'
        else:
            proto = 'http'

        if port in (80, 443):
            self.url = "%s://%s" % (proto, server)
        else:
            self.url = "%s://%s:%s" % (proto, server, port)

        self._login = False
        self._headers = {}

        # The refresh token may be used in case
        # the access token as expired
        self.__refresh_token = None

        if api_key:
            self._headers = {
                'Content-Type': 'application/json; charset=utf-8',
                'X-API-KEY': api_key
            }
            self.schema()

        # Variable populated by the login:
        self._user_id = None

        # Variable populated by the conversation
        self._cid = None

    @property
    def admin_url(self):
        """Returns the URL of the Kbot Administration view"""
        return "%s/admin" % self.url

    @property
    def chat_url(self):
        """Returns the default URL of the Kbot chat view"""
        return "%s" % self.url

    @property
    def avatar_url(self):
        return "%s/images/kbot_avatar.png" % self.url

    def login(self, username, password=None, timeout=5):
        """Login to local channel"""
        data = {}
        data['username'] = username
        data['usertype'] = 'local'
        if password is not None:
            data['password'] = password
        else:
            print("WARNING!!! Password is not set!!! Trying to use username...")
            data['password'] = username

        headers = {}
        headers['Content-Type'] = 'application/json; charset=utf-8'

        url = self.url + '/api/login'
        r = requests.post(url, headers=headers, data=json.dumps(data), timeout=timeout, verify=self.verify)

        r.raise_for_status()

        self.__reset_headers(r.json())
        self.schema()

    def impersonate(self, username, usertype='local', external_auth='', userdata=None, timeout=5):
        """Impersonate the given user"""

        r = self.request("post", "user/impersonate",
            data={
                "username": username,
                "im_type": usertype,
                "external_auth": external_auth,
                "userdata": userdata or {}},
            timeout=timeout)

        r.raise_for_status()

        self.__reset_headers(r.json())
        # After we impersonnate, we need to remove the original API KEY
        if "X-API-KEY" in self._headers:
            del self._headers["X-API-KEY"]

        self.schema()

    def schema(self):
        """Retrieve the public schema of kbot and builds python method for each of the defined end points"""
        r = self.get('schema')
        r.raise_for_status()

        j = r.json()

        self.version = j.get("version")

        for epoint in j.get('endpoints', []):
            if epoint['name'] != 'schema':
                self.__add_method(epoint['method'], epoint['name'], epoint['path'], epoint['params'], epoint['data'], epoint.get('description', ''))

    def __reset_headers(self, js):
        """
            Called when a login or impersonate end point is called.  Then expecting to get a json with:
                - access_token
                - refresh_token
            Or in the case of a refresh call. Then we only get a json with:
                - access_token

            The header content is ajusted with the token information from the json
        """
        if not self._headers:
            self._headers = {}
            self._headers['Content-Type'] = 'application/json; charset=utf-8'

        if js.get('access_token'):
            self._headers['Authorization'] = js['access_token']

        # The refresh token will be used by the refresh_token method later if the access token expires
        if js.get('refresh_token'):
            self.__refresh_token = js['refresh_token']

        self._login = True
        if js.get("user_id"):
            self._user_id = js['user_id']

    def __add_method(self, method: str, name: str, path: str, params: list, data: list, description: str):
        """Method to add a new dynamic method, based on the schema. This provides "python method" wrapper
           on top of the kbot APIs
        """
        def endpoint(*args, **kwargs):
            """Invoke request to endpoint"""
            rargs = {}
            for aname, values in (('params', params), ('data', data)):
                rargs[aname] = {}
                for value in values:
                    if value['mandatory'] and value['name'] not in kwargs:
                        raise RuntimeError("Missed attribute '%s' in '%s'" % (value['name'], aname))
                    # pylint: disable=eval-used
                    if value['name'] in kwargs:
                        if not isinstance(kwargs[value['name']], eval(value['type'])):
                            raise RuntimeError("Invalid type of attribute '%s'" % (value['name']))
                        v = kwargs[value['name']]
                    elif value['name'] not in kwargs and value['default'] is not None:
                        v = value['default']
                    else:
                        continue
                    rargs[aname][value['name']] = v
            return self.__request(method, uri=path % args, **rargs)
        endpoint.__doc__ = description
        endpoint.__name__ = name
        setattr(self, name, endpoint)

    def __refresh(self):
        r = requests.post(self.url + "/api/refresh",
                          data=json.dumps({"refresh_token": self.__refresh_token}),
                          headers=self._headers, timeout=5)
        r.raise_for_status()
        self.__reset_headers(r.json())

    def __request(self, method: str, uri : str = None, data: dict = None, params: dict = None, files: dict = None, attempt=0,  timeout=None):
        if files:
            # For file upload, the data must be a dictionnary
            dump_data = data
        else:
            dump_data = json.dumps(data or {})

        if files:
            headers = self._headers.copy()
            del headers['Content-Type']
            headers['Accept'] = "*/*"
        else:
            headers = self._headers

        r = requests.request(method.upper(), self.url + '/api/%s/' % (
            uri), params=params, data=dump_data, headers=headers, files=files, verify=self.verify, timeout=timeout)

        if r.status_code == 401:
            # Refresh the token
            try:
                self.__refresh()
            except Exception as e:

                # We try 3 times at the most
                if attempt == 3:
                    raise e

                time.sleep(3)

            # Re-invoke the request
            r = self.__request(method, uri=uri, data=data, params=params, attempt=attempt+1)

        return r

    def request(self, method: str, uri: str, data: dict = None, params: dict = None, files: dict = None, timeout=None):
        return self.__request(method, uri=uri, data=data, params=params, files=files, timeout=timeout)

    def unit(self, name: str, params=None, timeout=None) -> dict:
        r = self.get(name, params, timeout=timeout)
        if r:
            return r.json()
        return None

    def message(self, cid: int, message: str, timeout: int=60) -> list:
        response = []

        data = {'type': 'message', 'message': message}
        r = self.request("post", f'conversation/{cid}/message', data, timeout=timeout)

        r.raise_for_status()

        curtime = time.time()
        while timeout > 0:
            r = self.get(f'conversation/{cid}', timeout=timeout)

            r.raise_for_status()

            j = r.json()
            for resp in j:
                if resp['type'] == 'message':
                    # It's possible that bot will send several message to one input
                    response.append(resp)
                elif resp['type'] in ('stop_topic', 'wait_user_input'):
                    # Bot stop to process
                    # - stop_topic : bot stop to process message and ready for new topic
                    # - wait_user_input : bot asked the question and wait for user answer
                    timeout = 0
            timeout = timeout + curtime - time.time()
        return response

    def logout(self, timeout=None):
        """Logout from local channel"""
        if self._login:

            # If we have an open conversation, close it.
            # if self._cid:
            # What for?
            #     self._process('logout', 1)

            # Logout from the APIs
            self.request("post", self.url + '/api/logout', timeout=timeout)

    #
    # In addition to the Generated and built in API methods, we have the classic base REST methods
    #
    def get(self, unit, params=None, timeout=None):
        return self.__request("get", unit, params=params, timeout=timeout)

    def put(self, unit, data=None, timeout=None):
        return self.__request("put", unit, data=data, timeout=timeout)

    def post(self, unit, data=None, params=None, timeout=None):
        return self.__request("post", unit, data=data, params=params, timeout=timeout)

    def delete(self, unit, params=None, timeout=None):
        return self.__request("delete", unit, params=params, timeout=timeout)

    def post_file(self, unit, data, params=None, files=None, timeout=None):
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
        return self.__request("post", unit, params=params, data=data, files=files, timeout=timeout)

class UpKbotClient(Client):
    """Represents a currently reachable Kbot instance"""


class DownKbotClient(Client):
    """Represents a currently not reachable Kbot instance"""

    def __init__(self, server, port=443, proto='http', error=''):
        super().__init__(server, port=port, proto=proto)
        self.error = error
