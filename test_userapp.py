import re
import unittest
from unittest.mock import MagicMock, patch
from io import StringIO
from configparser import ConfigParser

import bottle
import boddle

import userapp

sample_config = """
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

[smtp]
host = mailhost.domain.com
port = 465
"""

userapp.UserSpace = MagicMock(name="MockUserSpace")
userapp.UserSpace.return_value = MagicMock(name="MockUserSpace instance")


class TestWebApp(unittest.TestCase):
    def test_initialisation_noargs(self):
        """We can create a WebApp without arguments"""
        wa = userapp.WebApp()
        self.assertTrue(isinstance(wa, bottle.Bottle))

    def _check_configuration(self, wa):
        """Check the sample configuration above."""
        self.assertEqual(wa.appname, "SAMPLE")
        self.assertEqual(wa.cookie_name, "sample_session_id")
        self.assertEqual(str(wa.root_dir), "/opt/webapp/dir")
        self.assertEqual(str(wa.login_page), "/opt/webapp/dir/html/login.html")

        db_expected = {
            "host": "localhost",
            "port": "5432",
            "user": "sampleuser",
            "password": "sampleuser",
        }
        userapp.UserSpace.assert_called_with("SAMPLE", **db_expected)

        smtp_expected = {
            "host": "mailhost.domain.com",
            "port": "465",
        }
        self.assertEqual(wa.smtp, smtp_expected)

    def test_initialisation_config_iterable(self):
        """We can create WebApp with iterable on str configuration"""
        wa = userapp.WebApp(config=sample_config.strip().split("\n"))
        self.assertTrue(isinstance(wa, bottle.Bottle))
        self._check_configuration(wa)

    def test_initialisation_config_fileobject(self):
        """We can create WebApp with file-like object configuration"""
        fobj = StringIO(sample_config)
        wa = userapp.WebApp(config=fobj)
        self.assertTrue(isinstance(wa, bottle.Bottle))
        self._check_configuration(wa)

    def test_initialisation_config_filename(self):
        """We can create WebApp with config filename"""
        with patch("userapp.pathlib.Path") as mock:
            pth = mock.return_value
            pth.open = MagicMock(
                name="pathlib.Path.open()", return_value=StringIO(sample_config)
            )

            wa = userapp.WebApp(config="/path/to/sample.conf")
            self.assertTrue(isinstance(wa, bottle.Bottle))
            mock.assert_any_call("/path/to/sample.conf")

    def test_configure_after_creation(self):
        """We can configure a WebApp after creation"""
        wa = userapp.WebApp()
        self.assertTrue(isinstance(wa, bottle.Bottle))
        cp = ConfigParser()
        cp.read_file(sample_config.split("\n"))
        wa.configure(cp)
        self._check_configuration(wa)

    def test_authenticated_returns_login(self):
        """request to authenticated method returns the default login page"""
        callback = MagicMock("wrapped function")
        wa = userapp.WebApp(config=sample_config.split("\n"))
        with boddle.boddle():
            authfunc = wa.authenticated(callback)
            def_login = authfunc()
            self.assertEqual(userapp.DEFAULT_LOGIN_HTML.format(None), def_login)

    def test_authenticated_cookie_name(self):
        """authenticated method with cookie set results in method called"""
        callback = MagicMock("wrapped function")
        br = userapp.bottle.request
        userapp.bottle.request = MagicMock(name="bottle.request")
        userapp.bottle.request.cookies = dict(sample_session_id="skjasldkajd")

        wa = userapp.WebApp(config=sample_config.split("\n"))
        wa.userspace.check_key = MagicMock(
            name="UserSpace.check_key()", return_value=(userapp.OK, "user1", 24, None)
        )

        authfunc = wa.authenticated(callback)
        authfunc()
        callback.assert_called_with()

        userapp.bottle.request = br

    def test_authenticated_header_key(self):
        """authenticated method with Bearer authorization results in method called"""
        callback = MagicMock("wrapped function")
        br = userapp.bottle.request
        userapp.bottle.request = MagicMock(name="bottle.request")
        userapp.bottle.request.headers = {"Authorization": "Bearer skjasldkajd"}

        wa = userapp.WebApp(config=sample_config.split("\n"))
        wa.cookie_name = None
        wa.userspace.check_key = MagicMock(
            name="UserSpace.check_key()", return_value=(userapp.OK, "user1", 24, None)
        )

        authfunc = wa.authenticated(callback)
        authfunc()
        callback.assert_called_with()

        userapp.bottle.request = br

    def test_login_bearer_json(self):
        """post_login with no cookie returns json object"""
        wa = userapp.WebApp(config=sample_config.split("\n"))
        wa.cookie_name = None
        wa.userspace.validate_user = MagicMock(
            name="validate_user()", return_value=("skjasldkajd", False, 24)
        )
        expected = {
            "rc": 200,
            "text": "OK",
            "token_type": "Bearer",
            "access_token": "skjasldkajd",
        }
        with boddle.boddle(
            headers={"Content-type": "application/json"},
            json={"username": "user21", "password": "xyzzy", "proceed": "/"},
        ):
            ret = wa.post_login()
            self.assertEqual(ret, expected)

    def test_login_cookie_json(self):
        """post_login with cookie name redirects"""
        wa = userapp.WebApp(config=sample_config.split("\n"))
        wa.userspace.validate_user = MagicMock(
            name="validate_user()", return_value=("skjasldkajd", False, 24)
        )
        with boddle.boddle(
            headers={"Content-type": "application/json"},
            json={"username": "user21", "password": "xyzzy", "proceed": "/url"},
        ):
            with self.assertRaises(userapp.bottle.HTTPResponse) as rsp:
                wa.post_login()

            self.assertIsNotNone(
                re.search("^Location: .*/url", repr(rsp.exception), re.MULTILINE)
            )
            self.assertTrue(
                "Set-Cookie: sample_session_id=skjasldkajd" in repr(rsp.exception)
            )

    def test_login_error_if_auth_fails(self):
        """post_login with bad credentials raises Error 401"""
        wa = userapp.WebApp(config=sample_config.split("\n"))
        wa.userspace.validate_user = MagicMock(
            name="validate_user()", return_value=("", False, None)
        )
        with boddle.boddle(
            headers={"Content-type": "application/json"},
            json={"username": "user21", "password": "xyzzy", "proceed": "/url"},
        ):
            with self.assertRaises(userapp.bottle.HTTPError) as rsp:
                wa.post_login()

            self.assertEqual(rsp.exception._status_code, 401)
            self.assertEqual(rsp.exception.body, "Bad credentials for user 'user21'")


if __name__ == "__main__":
    unittest.main()
