import os
import pgpubsub
import random
import time
import string

def get_env_variable(name):
    try:
        return os.environ[name]
    except KeyError:
        message = "Expected environment variable '{}' not set.".format(name)
        raise Exception(message)

# get env vars
POSTGRES_URL = "postgres:5432"
POSTGRES_USER = get_env_variable("POSTGRES_USER")
POSTGRES_PW = get_env_variable("POSTGRES_PASSWORD")
POSTGRES_DB = get_env_variable("POSTGRES_DB")
PUBSUB_CHANNEL = get_env_variable("PUBSUB_CHANNEL")

DB_URL = 'postgresql+psycopg2://{user}:{pw}@{url}/{db}'.format(user=POSTGRES_USER,pw=POSTGRES_PW,url=POSTGRES_URL,db=POSTGRES_DB)

pubsub = pgpubsub.connect(user=POSTGRES_USER, password=POSTGRES_PW, host="postgres", dbname=POSTGRES_DB)

while True:
    msg = ''.join(random.choices(string.ascii_uppercase + string.digits, k=64))
    pubsub.notify(PUBSUB_CHANNEL, msg)
    time.sleep(1)