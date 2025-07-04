import pathlib
import inspect
from configparser import ConfigParser

import bottle

from pgusers import UserSpace, OK, NOT_FOUND, REJECTED


class UserAppException(Exception):
    pass


class BadUserspaceError(UserAppException):
    pass

class PluginError(Exception):
    pass


VERSION = "0.9.9"


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
DEFAULT_ERROR_HTML = """
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>BAD CREDENTIALS</title>
  </head>
  <body>
      <div class="container">
        <h3>Bad credentials</h3>
        <p>Bad credentials for user '<i>{0}</i>'</p>
        <br>
        <p><a href="{1}">Try again</a>
      </div>
  </body>
</html>
"""


class Odre:
    """
    Middleware class that includes user
    authentication based on the pgusers module.
    """

    name = "odre"
    api = 2

    # framework_init = {
        # "bottle": self.add_bottle_routes,
        # "fastapi": lambda: None,
        # }

    def __init__(self, config, keyword="userinfo", prefix=""):
        """
        Initialises an Odre object

        Optional keyword arguments:
        config - Either a filename (str), or an iterable yielding
                 strings (e.g. an open file) a ConfigParser object, or None
        keyword - plugin keyword.
        prefix - prefix to add to the pre-defined api entry points. Your
                 html forms must use the with this prefix in the 'action'
                 attribute.

        if config is not given, the app must be configured using the
        configure() method

        odre = Odre(fw_type="bottle")
        """
        cp = None
        self.keyword = keyword
        self.prefix = prefix

        if isinstance(config, ConfigParser):
            cp = config
        elif isinstance(config, str):  # conf is a filename
            cp = ConfigParser()
            p = pathlib.Path(config)
            with p.open() as cf:
                cp.read_file(cf)
        elif isinstance(config, dict):  # dictionary of the form
             cp = config                # { "userspace": { "dbname": "XXX",
                                        #                   "user": "YYY",
                                        #                   "password": "ZZZ",
                                        #                   "host": "UUU",
                                        #                   "port": "VVV"}}
        elif config is not None:
            # conf is a file like object or iterable yielding strings
            #  with the format of an .ini file
            cp = ConfigParser()
            cp.read_file(config)

        if cp:
            self.configure(cp)

    def setup(self, app):

        for other in app.plugins:
            if not isinstance(other, Odre): continue
            if other.keyword == self.keyword:
                raise PluginError("Found another Odre plugin with "
                f"conflicting settings (non-unique keyword '{self.keyword}').")

        # fw_init_method = framework_init.get(fw_type, lambda: None)
        # fw_init_method()
        self.add_bottle_routes(app)

    def add_bottle_routes(self, app):
        app.route(self.prefix + "/login", method="POST", callback=self.bottle_post_login, skip=[Odre])
        app.route(self.prefix + "/logout", method="POST", callback=self.bottle_post_logout, skip=[Odre])
        app.route(self.prefix + "/changepassword", method="POST", callback=self.bottle_post_change_password, skip=[Odre])

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
        lf = appsection.get("login_page")
        if lf:
            self.login_page = pathlib.Path(lf)
        else:
            self.login_page = None

        ep = appsection.get("bad_credentials_page")
        if ep:
            self.bad_credentials_page = pathlib.Path(ep)
        else:
            self.bad_credentials_page = None

        userspace = cp["userspace"]
        self.userspace = UserSpace(**userspace)

        self.odre_config = cp

    def _get_session_key(self):
        """
        Get the session key from the request
        """
        key = ""
        if self.cookie_name:
            key = bottle.request.cookies.get(self.cookie_name)
        else:
            auth_hdr = bottle.request.headers.get("Authorization", "")
            if auth_hdr.startswith("Bearer"):
                key = auth_hdr.split(" ")[1]
        return key

    def _get_session_data(self):
        """
        Get the data associated to the session: username, userid, and
        any extra data associated to the session
        """
        key = self._get_session_key()
        if key:
            return self.userspace.check_key(key)
        return NOT_FOUND, "", 0, None

    def apply(self, callback, route):
        """
        Apply a decorator that checks whether the user is authenticated.

        If the request sends the expected cookie with the session key, or
        if it sends an "Authorization: Bearer <key>" header, it will check
        the validity of the key prior to running the callback.
        If not valid, the login method is called.
        """
        keyword = self.keyword

        # Test if the original callback accepts the keyword.
        # Ignore it if it does not need a database handle.
        args = inspect.signature(route.callback).parameters
        if keyword not in args:
            return callback

        def wrapper(*args, **kwargs):
            udata = self.get_user_data()
            if udata is not None:
                kwargs[keyword] = udata
                return callback(*args, **kwargs)

            url = bottle.request.url
            return self.login(url)

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

    def bottle_post_login(self, extra=None):
        """
        Callback for the /login route.

        Extracts the fields username, password and proceed, does the
        authentication and, if successful, redirects to proceed.
        """
        content_type = bottle.request.headers["Content-type"]
        url = bottle.request.url

        if content_type == "application/json":
            json_used = True
            jsn = bottle.request.json
            username = jsn.get("username", "")
            password = jsn.get("password", "")
            proceed = jsn.get("proceed", url)
        else:
            json_used = False
            username = bottle.request.forms.get("username", "")
            password = bottle.request.forms.get("password", "")
            proceed = bottle.request.forms.get("proceed", url)

        target = proceed

        key, admin, uid = self.userspace.validate_user(username, password, extra)
        if key and self.cookie_name:
            bottle.response.set_cookie(self.cookie_name, key, path="/", samesite="lax")
            bottle.redirect(target)

        if key:
            return dict(rc=200, text="OK", token_type="Bearer", access_token=key)
        if json_used:
            raise bottle.HTTPError(
                status=401, body=f"Bad credentials for user '{username}'"
            )
        else:
            if not self.bad_credentials_page:
                error_html = DEFAULT_ERROR_HTML.format(username, proceed)
            else:
                with self.bad_credentials_page.open() as fd:
                    error_html = fd.read().format(username, proceed)
            return error_html

    def bottle_post_logout(self):
        """callback for the /logout route"""
        _, _, uid, _ = self._get_session_data()
        if uid:
            self.userspace.kill_sessions(uid)

        if self.cookie_name:
            bottle.response.delete_cookie(self.cookie_name)
        bottle.redirect("/")

    def bottle_post_change_password(self):
        """callback for the /changepassword route"""
        content_type = bottle.request.headers["Content-type"]

        if content_type == "application/json":
            json_used = True
            jsn = bottle.request.json
            oldpassword = jsn.get("oldpassword", "")
            newpassword1 = jsn.get("newpassword1", "")
            newpassword2 = jsn.get("newpassword2", "")
        else:
            json_used = False
            oldpassword = bottle.request.forms.get("oldpassword", "")
            newpassword1 = bottle.request.forms.get("newpassword1", "")
            newpassword2 = bottle.request.forms.get("newpassword2", "")

        rc, username, userid, _ = self._get_session_data()
        if rc != OK:
            self.post_logout()

        if newpassword1 != newpassword2:
            raise bottle.HTTPError(status=400, body="New passwords don't match")

        rc = self.userspace.change_password(userid, newpassword1, oldpassword)
        if rc == REJECTED:
            raise bottle.HTTPError(status=401, body="Bad old password")

        if rc == NOT_FOUND:
            self.post_logout()

        return dict(rc=200, text="OK", message="Password changed")
