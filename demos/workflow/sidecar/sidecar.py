import json
import hashlib
import docker
import os
import sys 
import time
import shutil
import uuid
import requests
from celery import Celery
from concurrent.futures import ThreadPoolExecutor
from pymongo import MongoClient
import gridfs
import redis

env=os.environ

CELERY_BROKER_URL=env.get('CELERY_BROKER_URL','amqp://z43:z43@rabbit:5672'),
CELERY_RESULT_BACKEND=env.get('CELERY_RESULT_BACKEND','rpc://')

celery= Celery('tasks',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND)


io_dirs = {}
pool = ThreadPoolExecutor(1)

r = redis.StrictRedis(host="redis", port=6379)
r.flushall()
r.set('count', 0)
def delete_contents(folder):
    for the_file in os.listdir(folder):
        file_path = os.path.join(folder, the_file)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path): shutil.rmtree(file_path)
        except Exception as e:
            print(e)

def create_directories(task_id):
    global io_dirs
    for d in ['input', 'output', 'log']:
        dir = os.path.join("/", d, task_id)
        io_dirs[d] = dir
        if not os.path.exists(dir):
            os.makedirs(dir)
        else:
            delete_contents(dir)


def parse_input_data(data):
    global io_dirs 
    for d in data:
        if "type" in d and d["type"] == "url":
            r = requests.get(d["url"])
            filename = os.path.join(io_dirs['input'], d["name"])
            with open(filename, 'wb') as f:
                f.write(r.content)
    filename = os.path.join(io_dirs['input'], 'input.json')
    with open(filename, 'w') as f:
        f.write(json.dumps(data))
                
def fetch_container(data):
    image_name = data['name']
    image_tag = data['tag']
    client = docker.from_env(version='auto')
    client.login(registry="masu.speag.com/v2", username="z43", password="z43")
    client.images.pull(image_name, tag=image_tag)
    docker_image_name = image_name + ":" + image_tag
    return docker_image_name

def prepare_input_and_container(data):
    docker_image_name = ""
    if 'input' in data:
        parse_input_data(data['input'])

    if 'container' in data:
        docker_image_name = fetch_container(data['container'])

    return docker_image_name

def _bg_job(task, task_id):
    if not r.exists('log'):
        r.lpush('log', 'This is gonna be the log')

    for i in range(100):
        task.update_state(task_id=task_id, state='PROGRESS', meta={'process_percent': i})
        time.sleep(0.1)
        r.incr("count")
        r.rpush('log', ("This is a log meessage from the service: current # " + str(r.get("count").decode('utf-8'))).encode('utf-8'))
    
def start_container(task, task_id, docker_image_name, stage, io_env):
    client = docker.from_env(version='auto')
    fut = pool.submit(_bg_job(task, task_id))

    client.containers.run(docker_image_name, "run", 
         detach=False, remove=True,
         volumes = {'workflow_input'  : {'bind' : '/input'}, 
                    'workflow_output' : {'bind' : '/output'},
                    'workflow_log'    : {'bind'  : '/log'}},
         environment=io_env)

    # hash output
    output_hash = hash_job_output()

    store_job_output(output_hash)

    while not fut.done():
        time.sleep(1)
    
    return output_hash

def hash_job_output():
    output_hash = hashlib.sha256()
    directory = io_dirs['output']

    if not os.path.exists (directory):
        return -1

    try:
        for root, dirs, files in os.walk(directory):
            for names in files:
                filepath = os.path.join(root,names)
                try:
                    f1 = open(filepath, 'rb')
                except:
                    # You can't open the file for some reason
                    f1.close()
                    continue

                while 1:
                    # Read file in as little chunks
                    buf = f1.read(4096)
                    if not buf : break
                    output_hash.update(buf)
                f1.close()
    except:
        import traceback
        # Print the stack traceback
        traceback.print_exc()
        return -2

    return output_hash.hexdigest() 

def store_job_output(output_hash):
    db_client = MongoClient("mongodb://database:27017/")
    output_database = db_client.output_database
    output_collections = output_database.output_collections
    file_db = db_client.file_db
    fs = gridfs.GridFS(file_db)
    directory = io_dirs['output']
    data = {}
    if not os.path.exists (directory):
        return
    try:
        output_file_list = []
        ids = []
        for root, dirs, files in os.walk(directory):
            for names in files:
                filepath = os.path.join(root,names)
                file_id = fs.put(open(filepath,'rb'))
                ids.append(file_id)
                with open(filepath, 'rb') as f:
                    file_data = f.read()
                    current = { 'filename' : names, 'contents' : file_data }
                    output_file_list.append(current)

        data["output"] = output_file_list
        data["_hash"] = output_hash
        data["ids"] = ids

        output_collections.insert_one(data)

    except:
        import traceback
        # Print the stack traceback
        traceback.print_exc()
        return -2

def do_run(task, task_id, data):
    docker_image_name = prepare_input_and_container(data)
    io_env = []
    io_env.append("INPUT_FOLDER=/input/"+task_id)
    io_env.append("OUTPUT_FOLDER=/output/"+task_id)
    io_env.append("LOG_FOLDER=/log/"+task_id)
 
  
    return start_container(task, task_id, docker_image_name, "run", io_env)

@celery.task(name='mytasks.run', bind=True)
def run(self, data):
    task = self
    task_id = task.request.id

    create_directories(task_id)
    
    return str(do_run(task, task_id, data))

