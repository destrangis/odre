import bottle

from pgusers import UserSpace
from userapp import WebApp


ussp = UserSpace(database="SAMPLE",
                user="sampleuser",
                password="sampleuser",
                host="localhost")

if not ussp.find_user(username="paco"):
    ussp.create_user("paco", "porro23", "paco@perro.pi", {})

sample = WebApp(cookie="sample_session_id")
sample.set_userspace(ussp)

@sample.get("/hello/<name>")
@sample.authenticated
def hello(name):
    return f"<p>Hello <b>{name}</b></p>"

@sample.get("/")
def main():
    return "<h3>Hello world</h3>"

if __name__ == "__main__":
    bottle.run(sample)
