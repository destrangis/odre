import pathlib
from configparser import ConfigParser

import bottle

from pgusers import UserSpace, OK, NOT_FOUND


class UserAppException(Exception):
    pass


class BadUserspaceError(UserAppException):
    pass


VERSION = "0.9.0"


DEFAULT_LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>LOGIN</title>
  </head>
  <body>
    <form action="/login" method="post">
      <div class="container">
        <label for="uname"><b>Username</b></label>
        <input type="text" placeholder="Enter Username" name="username" required/>

        <label for="password"><b>Password</b></label>
        <input type="password" placeholder="Enter Password" name="password" required/>

        <input type="hidden" name="proceed" value="{0}" />

        <button type="submit">Login</button>
        <!--
        <label>
          <input type="checkbox" checked="checked" name="remember"/> Remember me
        </label>
        -->
      </div>
    </form>
  </body>
</html>
"""


class Odre(bottle.Bottle):
    """
    Web Application class derived from Bottle that includes user
    authentication based on the pgusers module.

    All Odre instances include a /login route that performs the
    user authentication.

    The class also provides an 'authenticated' decorator to do the
    authentication automatically, e.g:

    myapp = Odre(userspace=usp)
    @myapp.get("/books/<bookid>")
    @myapp.authenticated
    def get_books(bookid)
        ...
    """

    def __init__(self, *args, **kwargs):
        """
        Initialises an Odre object

        Optional keyword arguments:
        config - Either a filename (str), or an iterable yielding
                 strings (e.g. an open file) a ConfigParser object, or None

        if config is not given, the app must be configured using the
        configure() method
        """
        cp = None
        conf = kwargs.pop("config", None)

        super().__init__(*args, **kwargs)
        self.route("/login", method="POST", callback=self.post_login)

        if isinstance(conf, ConfigParser):
            cp = conf
        elif isinstance(conf, str):  # conf is a filename
            cp = ConfigParser()
            p = pathlib.Path(conf)
            with p.open() as cf:
                cp.read_file(cf)
        elif conf is not None:
            # conf is a file like object or iterable yielding strings
            cp = ConfigParser()
            cp.read_file(conf)

        if cp:
            self.configure(cp)

    def configure(self, cp):
        """
        Configure the application
        Args:
        cp - a ConfigParser object or any mapping object containing the
             sections with their keys and their values
        """
        appsection = cp["app"]
        self.appname = appsection["name"]
        self.cookie_name = appsection.get("cookie_name", None)
        self.root_dir = pathlib.Path(appsection["root_dir"])
        self.login_page = None
        lf = appsection.get("login_page")
        if lf:
            self.login_page = pathlib.Path(lf)

        database = cp["database"]
        userspace = cp["userspace"]
        usname = userspace["name"]
        self.userspace = UserSpace(usname, **database)

        self.smtp = dict(**cp["smtp"])

    def _get_session_data(self):
        """
        Get the data associated to the session: username, userid, and
        any extra data associated to the session
        """
        key = ""
        if self.cookie_name:
            key = bottle.request.cookies.get(self.cookie_name)
        else:
            auth_hdr = bottle.request.headers.get("Authorization", "")
            if auth_hdr.startswith("Bearer"):
                key = auth_hdr.split(" ")[1]

        if key:
            return self.userspace.check_key(key)
        return NOT_FOUND, "", 0, None

    def authenticated(self, callback):
        """
        Decorator that checks whether the user is authenticated.

        If the request sends the expected cookie with the session key, or
        if it sends an "Authorization: Bearer <key>" header, it will check
        the validity of the key prior to running the callback.
        If not valid, the login method is called.
        """

        def wrapper(*args, **kwargs):
            (rc, uname, uid, data) = self._get_session_data()
            if rc == OK:
                return callback(*args, **kwargs)

            path_info = bottle.request.environ.get("PATH_INFO")
            return self.login(path_info)

        return wrapper

    def get_user_data(self):
        """
        Find data about a the session user
        """
        rc, uname, uid, session_data = self._get_session_data()
        if rc == OK:
            udata = self.userspace.find_user(userid=uid)
            udata["session_data"] = session_data
            return udata

        return None

    def login(self, path):
        """
        Return the html code for the login page.
        The login page should contain a form with the fields
        "username", "password", and the hidden field "proceed", which
        is the relative URL to go once the authentication is successful.
        """
        if self.login_page and self.login_page.is_file():
            with self.login_page.open() as lp:
                loginhtml = lp.read()
        else:
            loginhtml = DEFAULT_LOGIN_HTML

        return loginhtml.format(path)

    def post_login(self, extra=None):
        """
        Callback for the /login route.

        Extracts the fields username, password and proceed, does the
        authentication and, if successful, redirects to proceed.
        """
        content_type = bottle.request.headers["Content-type"]

        if content_type == "application/json":
            jsn = bottle.request.json
            username = jsn.get("username", "")
            password = jsn.get("password", "")
            proceed = jsn.get("proceed", "/")
        else:
            username = bottle.request.forms.get("username", "")
            password = bottle.request.forms.get("password", "")
            proceed = bottle.request.forms.get("proceed", "/")

        key, admin, uid = self.userspace.validate_user(username, password, extra)
        if key and self.cookie_name:
            bottle.response.set_cookie(self.cookie_name, key)
            bottle.redirect(proceed)

        if key:
            return dict(rc=200, text="OK", token_type="Bearer", access_token=key)
        else:
            raise bottle.HTTPError(
                status=401, body=f"Bad credentials for user '{username}'"
            )