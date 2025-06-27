====
Odre
====

Bottle plugin class that provides user authentication based on the ``pgusers`` module.

Usage
-----

You just need to import the ``Odre`` object, and use Bottle's ``install`` method to install an authentication wrapper to all the routes whose callback users the ``userinfo`` (or the keyword specified) parameter:

.. code-block:: python

    sample = bottle.Bottle()

    authenticated = Odre(config=config.split("\n"), keyword="userinfo")
    sample.install(authenticated)

    @sample.get("/hello/<name>")
    def hello(name, userinfo):
        return f"<p>Hello <b>{name} {userinfo}</b></p>"

In the example above, when the route ``/hello/<name>`` is accessed for the first time, the user is shown a login form asking for credentials. Upon successful authentication, the user is supplied a token that is set either in a cookie or the client should supply it in the form of an ``Authorization: Bearer <token>`` header. The function is then injected the user information in the ```userinfo``` argument.

.. _configuration:

Configuration
-------------

The configuration is an .ini file similar to the following example:

.. code-block:: ini

    [app]
    name = SAMPLE
    cookie_name = sample_session_id
    root_dir = /opt/webapp/dir
    login_page = /opt/webapp/dir/html/login.html

    [database]
    host = localhost
    port = 5432
    user = sampleuser
    password = sampleuser

    [userspace]
    name = SAMPLE
    # SAMPLE is a different database than the app database and it possibly
    # has different user, host, port etc.
    host = localhost
    port = 5432
    user = sampleuser
    password = sampleuser

    [smtp]
    host = mailhost.domain.com
    port = 465

The [app] section
~~~~~~~~~~~~~~~~~
:name:
  The name of the app. Must always be present.
:cookie_name:
  The name of the cookie that will be issued. This field is optional, if omitted the response to a successful login will be a json object with the token, which will be the responsibility of the front-end to send on every subsequent request in an ``Authorization: Bearer <token>`` header.
:root_dir:
  The root directory of the application. This is useful to locate the app's resources. Must always be present.
:login_page:
  The path to an html file that contains the login page. If omitted, a default login page will be issued, but it will be probably be too basic. The requirements for the login page are that it must send a form with the following fields: ``username``, ``password``, and ``proceed``. The ``proceed`` field must be a hidden file set to ``{0}`` so that ``Odre`` can substitute it for the path that was originally requested and, upon a successful login, redirect the user there. Alternatively, the front-end can log-in using the pre-installed ``/login`` route sending username and password in a json object with a ``Content-type`` header set to ``application/json``

The [userspace] section
~~~~~~~~~~~~~~~~~~~~~~~
:name:
  The name of the ``pgusers`` userspace. A *userspace*, is a PostgreSQL database that contains the users and sessions and is handled by the ``pgusers`` module.
:host:
  The host where the userspace resides. If omitted, a local connection through a unix-domain socket is assumed.
:port:
  The port where PostgreSQL userspace listens. If omitted, Postgres default port 5432 is assumed.
:user:
  The PostgreSQL user for the userspace.
:password:
  The password for the PostgreSQL user for the userspace.

The [database] section
~~~~~~~~~~~~~~~~~~~~~~
This section contains the parameters needed to connect to the app database. The fields are the same as those used to create a connection on the ``psycopg2`` module.

:host:
  The host where the PostgreSQL resides. If omitted, a local connection through a unix-domain socket is assumed.
:port:
  The port where PostgreSQL listens. If omitted, Postgres default port 5432 is assumed.
:user:
  The PostgreSQL user.
:password:
  The password for the PostgreSQL user.

The [smtp] section
~~~~~~~~~~~~~~~~~~
This section contains the SMTP server parameters to send the user a *reset password* token when such functionality is implemented.


The API
-------

``app = Odre(config, keyword="userinfo", prefix="")``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This is the class constructor. ``Odre`` is a plugin for ``Bottle`` The parameter ``config`` can be used to specify the app configuration_. It can be:

- A string, which is interpreted as a filename
- A ConfigParser object
- Any iterable yielding strings, e.g. a file-like object

The ``keyword`` parameter is the name of the variable that will be injected with the user information on authenticated routes.
The ``prefix`` parameter is an optional prefix for the routes that will be installed. E.g. if for any reason it's not desired to use ``/login`` as a route, we can give a value to prefix, for instance ``prefix = "/odre"`` so that the login function will be installed on ``/odre/login``.

``@app.authenticated``
~~~~~~~~~~~~~~~~~~~~~~
This decorator, applied before any route (i.e. *below* the routes) marks a
function as accessible only to authenticated users. If the route is being requested
for the first time, or without a valid session token specified either in the
cookie or in a bearer authorisation header, or the token has expired, the
route will return the login html page specified in the configuration, or a
basic, default login page. Example:

.. code-block:: python

    @app.get("/hello/<name>")
    @app.authenticated
    def hello(name):
        return f"<p>Hello <b>{name}</b></p>"

The ``/login`` pre-installed route
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Client apps that don't want to present the user with the login html page for
any reason, can always request the ``/login`` route via the ``POST`` http verb.
The route expects either a form with content type ``application/x-www-form-urlencoded``
or an ``application/json`` with the following fields:

:username:
  The username
:password:
  The password
:proceed:
  A relative URI to proceed to upon successful authentication. This field is optional
  and defaults to '/'



License
-------
This software is released with the **MIT License**
