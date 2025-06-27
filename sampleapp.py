import bottle
from odre import Odre

config = """
[app]
name = SAMPLE
cookie_name = sample_session_id
root_dir = /opt/webapp/dir
#login_page = /opt/webapp/dir/html/login.html

[database]
host = localhost
port = 5432
user = sampleuser
password = sampleuser

[userspace]
dbname = main
# the user is the user that can read/write the SAMPLE database
user = sampleuser
password = sampleuser
host = localhost
port = 5432

[smtp]
host = mailhost.zen.co.uk
port = 465
"""

sample = bottle.Bottle()

authenticated = Odre(config=config.split("\n"), keyword="userinfo")
sample.install(authenticated)


@sample.get("/hello/<name>")
def hello(name, userinfo):
    return f"<p>Hello <b>{name} {userinfo}</b></p>"


@sample.get("/")
def main():
    return "<h3>Hello world</h3>"


if __name__ == "__main__":
    bottle.run(sample)
