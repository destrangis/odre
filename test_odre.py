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
dbname = SAMPLE
user = sampleuser
password = sampleuser

[smtp]
host = mailhost.domain.com
port = 465
"""

odre.UserSpace = MagicMock(name="MockUserSpace")
odre.UserSpace.return_value = MagicMock(name="MockUserSpace instance")


class TestWebApp(unittest.TestCase):

    def _check_configuration(self, wa):
        """Check the sample configuration above."""
        self.assertEqual(wa.appname, "SAMPLE")
        self.assertEqual(wa.cookie_name, "sample_session_id")
        self.assertEqual(str(wa.root_dir), "/opt/webapp/dir")
        self.assertEqual(str(wa.login_page), "/opt/webapp/dir/html/login.html")

        userspace_expected = {
            "dbname": "SAMPLE",
            "user": "sampleuser",
            "password": "sampleuser",
        }
        odre.UserSpace.assert_called_with(**userspace_expected)

        smtp_expected = {
            "host": "mailhost.domain.com",
            "port": "465",
        }
        smtp_section = dict(**wa.odre_config["smtp"])
        self.assertEqual(smtp_section, smtp_expected)

    def test_initialisation_config_iterable(self):
        """We can create Odre with iterable on str configuration"""
        wa = odre.Odre(config=sample_config.strip().split("\n"))
        self._check_configuration(wa)

    def test_initialisation_config_fileobject(self):
        """We can create Odre with file-like object configuration"""
        fobj = StringIO(sample_config)
        wa = odre.Odre(config=fobj)
        self._check_configuration(wa)

    def test_initialisation_config_filename(self):
        """We can create Odre with config filename"""
        with patch("odre.pathlib.Path") as mock:
            pth = mock.return_value
            pth.open = MagicMock(
                name="pathlib.Path.open()", return_value=StringIO(sample_config)
            )

            wa = odre.Odre(config="/path/to/sample.conf")
            mock.assert_any_call("/path/to/sample.conf")

    def test_configure_after_creation(self):
        """We can configure a Odre after creation"""
        wa = odre.Odre({})
        cp = ConfigParser()
        cp.read_file(sample_config.split("\n"))
        wa.configure(cp)
        self._check_configuration(wa)

    def _get_callback_and_route(self):
        """return a callback and route, to run apply"""
        func = MagicMock("wrapped function")
        wrapped = lambda userinfo: func(userinfo)
        route = MagicMock()
        route.callback = wrapped
        return wrapped, route

    def test_authenticated_returns_login(self):
        """request to authenticated method returns the default login page"""
        wrapped, route = self._get_callback_and_route()
        plugin = odre.Odre(config=sample_config.split("\n"))
        with boddle.boddle(url="http://server.com/"):
            authfunc = plugin.apply(wrapped, route)
            def_login = authfunc()
            self.assertEqual(odre.DEFAULT_LOGIN_HTML.format("http://server.com/"), def_login)


if __name__ == "__main__":
    unittest.main()
