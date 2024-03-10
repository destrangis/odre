import re
import unittest
from unittest.mock import MagicMock, patch
from io import StringIO
from configparser import ConfigParser

import bottle
import boddle

import odre

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

odre.UserSpace = MagicMock(name="MockUserSpace")
odre.UserSpace.return_value = MagicMock(name="MockUserSpace instance")


class TestWebApp(unittest.TestCase):
    def test_initialisation_noargs(self):
        """We can create a Odre without arguments"""
        wa = odre.Odre()
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
        odre.UserSpace.assert_called_with("SAMPLE", **db_expected)

        smtp_expected = {
            "host": "mailhost.domain.com",
            "port": "465",
        }
        smtp_section = dict(**wa.config["smtp"])
        self.assertEqual(smtp_section, smtp_expected)

    def test_initialisation_config_iterable(self):
        """We can create Odre with iterable on str configuration"""
        wa = odre.Odre(config=sample_config.strip().split("\n"))
        self.assertTrue(isinstance(wa, bottle.Bottle))
        self._check_configuration(wa)

    def test_initialisation_config_fileobject(self):
        """We can create Odre with file-like object configuration"""
        fobj = StringIO(sample_config)
        wa = odre.Odre(config=fobj)
        self.assertTrue(isinstance(wa, bottle.Bottle))
        self._check_configuration(wa)

    def test_initialisation_config_filename(self):
        """We can create Odre with config filename"""
        with patch("odre.pathlib.Path") as mock:
            pth = mock.return_value
            pth.open = MagicMock(
                name="pathlib.Path.open()", return_value=StringIO(sample_config)
            )

            wa = odre.Odre(config="/path/to/sample.conf")
            self.assertTrue(isinstance(wa, bottle.Bottle))
            mock.assert_any_call("/path/to/sample.conf")

    def test_configure_after_creation(self):
        """We can configure a Odre after creation"""
        wa = odre.Odre()
        self.assertTrue(isinstance(wa, bottle.Bottle))
        cp = ConfigParser()
        cp.read_file(sample_config.split("\n"))
        wa.configure(cp)
        self._check_configuration(wa)

    def test_authenticated_returns_login(self):
        """request to authenticated method returns the default login page"""
        callback = MagicMock("wrapped function")
        wa = odre.Odre(config=sample_config.split("\n"))
        with boddle.boddle(url="http://server.com/"):
            authfunc = wa.authenticated(callback)
            def_login = authfunc()
            self.assertEqual(odre.DEFAULT_LOGIN_HTML.format("http://server.com/"), def_login)

    def test_authenticated_cookie_name(self):
        """authenticated method with cookie set results in method called"""
        callback = MagicMock("wrapped function")
        br = odre.bottle.request
        odre.bottle.request = MagicMock(name="bottle.request")
        odre.bottle.request.cookies = dict(sample_session_id="skjasldkajd")

        wa = odre.Odre(config=sample_config.split("\n"))
        wa.userspace.check_key = MagicMock(
            name="UserSpace.check_key()", return_value=(odre.OK, "user1", 24, None)
        )

        authfunc = wa.authenticated(callback)
        authfunc()
        callback.assert_called_with()

        odre.bottle.request = br

    def test_authenticated_header_key(self):
        """authenticated method with Bearer authorization results in method called"""
        callback = MagicMock("wrapped function")
        br = odre.bottle.request
        odre.bottle.request = MagicMock(name="bottle.request")
        odre.bottle.request.headers = {"Authorization": "Bearer skjasldkajd"}

        wa = odre.Odre(config=sample_config.split("\n"))
        wa.cookie_name = None
        wa.userspace.check_key = MagicMock(
            name="UserSpace.check_key()", return_value=(odre.OK, "user1", 24, None)
        )

        authfunc = wa.authenticated(callback)
        authfunc()
        callback.assert_called_with()

        odre.bottle.request = br

    def test_login_bearer_json(self):
        """post_login with no cookie returns json object"""
        wa = odre.Odre(config=sample_config.split("\n"))
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
        wa = odre.Odre(config=sample_config.split("\n"))
        wa.userspace.validate_user = MagicMock(
            name="validate_user()", return_value=("skjasldkajd", False, 24)
        )
        with boddle.boddle(
            headers={"Content-type": "application/json"},
            json={"username": "user21", "password": "xyzzy", "proceed": "/url"},
        ):
            with self.assertRaises(odre.bottle.HTTPResponse) as rsp:
                wa.post_login()

            self.assertIsNotNone(
                re.search("^Location: .*/url", repr(rsp.exception), re.MULTILINE)
            )
            self.assertTrue(
                "Set-Cookie: sample_session_id=skjasldkajd" in repr(rsp.exception)
            )

    def test_login_error_if_auth_fails(self):
        """post_login with bad credentials raises Error 401"""
        wa = odre.Odre(config=sample_config.split("\n"))
        wa.userspace.validate_user = MagicMock(
            name="validate_user()", return_value=("", False, None)
        )
        with boddle.boddle(
            headers={"Content-type": "application/json"},
            json={"username": "user21", "password": "xyzzy", "proceed": "/url"},
        ):
            with self.assertRaises(odre.bottle.HTTPError) as rsp:
                wa.post_login()

            self.assertEqual(rsp.exception._status_code, 401)
            self.assertEqual(rsp.exception.body, "Bad credentials for user 'user21'")

    @unittest.skip(
        "Boddle can't handle 'Content-type' headers other than 'application/json'"
    )
    def test_login_html_error(self):
        """post_login with bad credentials returns an html error page"""
        wa = odre.Odre(config=sample_config.split("\n"))
        wa.userspace.validate_user = MagicMock(
            name="validate_user()", return_value=("", False, None)
        )
        with boddle.boddle(
            headers={"Content-type": "application/x-www-form-urlencoded"},
            forms={"username": "user21", "password": "xyzzy", "proceed": "/url"},
        ):
            ret = wa.post_login()
            self.assertEqual(ret, odre.DEFAULT_ERROR_HTML.format("user21", "/url"))

    def test_logout(self):
        """post_logout calls kill_session"""
        wa = odre.Odre(config=sample_config.split("\n"))
        wa.userspace.check_key = MagicMock(
            name="check_key()", return_value=(odre.OK, "user1", 24, None)
        )
        wa.userspace.kill_sessions = MagicMock(name="kill_sessions()")

        with boddle.boddle(headers={"Cookie": "sample_session_id=skjasldkajd"}):
            with self.assertRaises(odre.bottle.HTTPResponse) as rsp:
                wa.post_logout()

            self.assertIsNotNone(
                re.search("^Location:", repr(rsp.exception), re.MULTILINE)
            )
            self.assertIsNotNone(
                re.search(
                    '^Set-Cookie: sample_session_id=""',
                    repr(rsp.exception),
                    re.MULTILINE,
                )
            )
            wa.userspace.kill_sessions.assert_called_once()

    def test_logout_with_bad_key(self):
        """logout with a bad key doesn't kill session, but still redirects"""
        wa = odre.Odre(config=sample_config.split("\n"))
        wa.userspace.check_key = MagicMock(
            name="check_key()", return_value=(odre.NOT_FOUND, None, None, None)
        )
        wa.userspace.kill_sessions = MagicMock(name="kill_sessions()")

        with boddle.boddle(headers={"Cookie": "sample_session_id=skjasldkajd"}):
            with self.assertRaises(odre.bottle.HTTPResponse) as rsp:
                wa.post_logout()

            self.assertIsNotNone(
                re.search("^Location:", repr(rsp.exception), re.MULTILINE)
            )
            self.assertIsNotNone(
                re.search(
                    '^Set-Cookie: sample_session_id=""',
                    repr(rsp.exception),
                    re.MULTILINE,
                )
            )
            wa.userspace.kill_sessions.assert_not_called()

    def test_change_password_with_good_password(self):
        """Change password can change password"""
        wa = odre.Odre(config=sample_config.split("\n"))
        wa.userspace.check_key = MagicMock(
            name="check_key()", return_value=(odre.OK, "user1", 24, None)
        )
        wa.userspace.change_password = MagicMock(
            name="change_password()", return_value=odre.OK
        )
        expected = dict(rc=200, text="OK", message="Password changed")

        with boddle.boddle(
            headers={
                "Content-type": "application/json",
                "Cookie": "sample_session_id=skjasldkajd",
            },
            json={
                "oldpassword": "xyzzy",
                "newpassword1": "wersaser",
                "newpassword2": "wersaser",
            },
        ):
            result = wa.post_change_password()

        self.assertEqual(result, expected)

    def test_change_password_with_bad_password(self):
        """Change password with bad oldpassword throws error 401"""
        wa = odre.Odre(config=sample_config.split("\n"))
        wa.userspace.check_key = MagicMock(
            name="check_key()", return_value=(odre.OK, "user1", 24, None)
        )
        wa.userspace.change_password = MagicMock(
            name="change_password()", return_value=odre.REJECTED
        )

        with boddle.boddle(
            headers={
                "Content-type": "application/json",
                "Cookie": "sample_session_id=skjasldkajd",
            },
            json={
                "oldpassword": "xyzzy",
                "newpassword1": "wersaser",
                "newpassword2": "wersaser",
            },
        ):
            with self.assertRaises(odre.bottle.HTTPError) as rsp:
                result = wa.post_change_password()

            self.assertEqual("401 Unauthorized", rsp.exception.status)

    def test_change_password_with_nonmatching_new_passwords(self):
        """Change passwords with non-matching keys throw error 400"""
        wa = odre.Odre(config=sample_config.split("\n"))
        wa.userspace.check_key = MagicMock(
            name="check_key()", return_value=(odre.OK, "user1", 24, None)
        )
        wa.userspace.change_password = MagicMock(
            name="change_password()", return_value=odre.REJECTED
        )

        with boddle.boddle(
            headers={
                "Content-type": "application/json",
                "Cookie": "sample_session_id=skjasldkajd",
            },
            json={
                "oldpassword": "xyzzy",
                "newpassword1": "wersasen",
                "newpassword2": "wersaser",
            },
        ):
            with self.assertRaises(odre.bottle.HTTPError) as rsp:
                result = wa.post_change_password()

            self.assertEqual("400 Bad Request", rsp.exception.status)


if __name__ == "__main__":
    unittest.main()
