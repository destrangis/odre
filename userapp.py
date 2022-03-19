import pathlib

import bottle

from pgusers import UserSpace, OK, NOT_FOUND

class UserAppException(Exception):
    pass

class BadUserspaceError(UserAppException):
    pass


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

class WebApp(bottle.Bottle):
    """
    Web Application class derived from Bottle that includes user
    authentication based on the pgusers module.

    All WebApp instances include a /login route that performs the
    user authentication.

    The class also provides an 'authenticated' decorator to do the
    authentication automatically, e.g:

    myapp = WebApp(userspace=usp)
    @myapp.get("/books/<bookid>")
    @myapp.authenticated
    def get_books(bookid)
        ...
    """

    def __init__(self, *args, **kwargs):
        """
        Initialises a WebApp object
        Optional keyword arguments:
        rootdir [pathlib.Path] - The root directory of the application
                                  where it can get it's configuration,
                                  files, etc.
        userspace [pgusers.UserSpace] - The userspace. Default None.
        appname [str] - A name for the app. By default the same as the
                         dbname in the userspace or "" if no userspace
        cookiename [str] - A name of a cookie on which to store authentication key.
                        If not specified, when a user is authenticated the key
                        is returned on a JSON response and the user is expected
                        to send further requests using the key in a header as in
                        Authorization: Bearer <key>
        """
        self.userspace = kwargs.pop("userspace", None)
        self.appname = kwargs.pop("appname", self.userspace.dbname if self.userspace else "")
        self.cookie_name = kwargs.pop("cookie", None)
        self.rootdir = pathlib.Path(__file__).parent

        super().__init__(*args, **kwargs)
        self.route("/login", method="POST", callback=self.post_login)


    def set_rootdir(self, dir):
        """
        Set the rootdir to something different from the default.
        """
        self.rootdir = pathlib.Path(dir)


    def set_userspace(self, usp):
        """
        Set the userspace
        """
        # if isinstance(usp, str):
            # self.userspace = pgusers.UserSpace(database=usp)
            # self.appname = usp
        if isinstance(usp, UserSpace):
            self.userspace = usp
            self.appname = usp.dbname
        else:
            raise BadUserspaceError("set_userspace: Expected UserSpace. "
                        f"Got [{usp.__class__.__name__}]:{repr(usp)}")


    def set_appname(self, name):
        """
        Set the appname
        """
        self.appname = name


    def authenticated(self, callback):
        """
        Decorator that checks whether the user is authenticated.

        If the request sends the expected cookie with the session key, or
        if it sends an "Authorization: Bearer <key>" header, it will check
        the validity of the key prior to running the callback.
        If not valid, the login method is called.
        """
        def wrapper(*args, **kwargs):
            key = ""
            if self.cookie_name:
                key = bottle.request.cookies.get(self.cookie_name)
            else:
                auth_hdr = bottle.request.headers.get("Authorization", "")
                if auth_hdr.startswith("Bearer"):
                    key = auth_hdr.split(" ")[1]

            rc = NOT_FOUND
            if key:
                (rc, uname, uid, data) = self.userspace.check_key(key)
            if rc == OK:
                return callback(*args, **kwargs)

            path_info = bottle.request.environ.get("PATH_INFO")
            return self.login(path_info)
        return wrapper


    def login(self, path):
        """
        Return the html code for the login page.
        The login page should contain a form with the fields
        "username", "password", and the hidden field "proceed", which
        is the relative URL to go once the authentication is successful.
        """
        loginpage = self.rootdir / "html" / "login.html"
        if loginpage.is_file():
            with loginpage.open() as lp:
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

        key, uid = self.userspace.validate_user(username, password, extra)
        if key and self.cookie_name:
            bottle.response.set_cookie(self.cookie_name, key)
            bottle.redirect(proceed)

        if key:
            return dict(rc=200, text="OK", token_type="Bearer", access_token=key)
        else:
            raise bottle.HTTPError(status=401, body=f"Bad credentials for user '{username}'")
