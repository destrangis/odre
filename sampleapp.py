import bottle

from userapp import WebApp

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
name = SAMPLE

[smtp]
host = mailhost.zen.co.uk
port = 465
"""

sample = WebApp(config=config.split("\n"))


@sample.get("/hello/<name>")
@sample.authenticated
def hello(name):
    return f"<p>Hello <b>{name}</b></p>"


@sample.get("/")
def main():
    return "<h3>Hello world</h3>"


if __name__ == "__main__":
    bottle.run(sample)
