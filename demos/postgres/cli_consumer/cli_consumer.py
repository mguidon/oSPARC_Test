from flask import Flask
import os
import pgpubsub

def get_env_variable(name):
    try:
        return os.environ[name]
    except KeyError:
        message = "Expected environment variable '{}' not set.".format(name)
        raise Exception(message)

# get env vars OR ELSE
POSTGRES_URL = "postgres:5432"
POSTGRES_USER = get_env_variable("POSTGRES_USER")
POSTGRES_PW = get_env_variable("POSTGRES_PASSWORD")
POSTGRES_DB = get_env_variable("POSTGRES_DB")
PUBSUB_CHANNEL = get_env_variable("PUBSUB_CHANNEL")


app = Flask(__name__)

DB_URL = 'postgresql+psycopg2://{user}:{pw}@{url}/{db}'.format(user=POSTGRES_USER,pw=POSTGRES_PW,url=POSTGRES_URL,db=POSTGRES_DB)

pubsub = pgpubsub.connect(user=POSTGRES_USER, password=POSTGRES_PW, host="postgres", dbname=POSTGRES_DB)



pubsub.listen(PUBSUB_CHANNEL)

while True:
    msg = ""
    e = pubsub.get_event()
    if not e is None:
        sender_pid = e.pid
        what = e.payload
        channel = e.channel
        msg = msg + "{} sent {} on {}".format(sender_pid, what, channel)
        print("Received message: {}".format(msg))