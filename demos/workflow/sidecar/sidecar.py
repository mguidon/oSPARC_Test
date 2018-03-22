import hashlib
import json
import os
import shutil
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import docker
import gridfs
import redis
import requests
from celery import Celery
from pymongo import MongoClient

env=os.environ

CELERY_BROKER_URL=env.get('CELERY_BROKER_URL','amqp://z43:z43@rabbit:5672'),
CELERY_RESULT_BACKEND=env.get('CELERY_RESULT_BACKEND','rpc://')

celery= Celery('tasks',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND)


io_dirs = {}
pool = ThreadPoolExecutor(1)
run_pool = True

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

#def _bg_job(task, task_id):
def _bg_job(task, task_id):
    global io_dirs

    log_key = task_id + ":log"
    prog_key = task_id + ":progress"
    if not r.exists(log_key):
        r.lpush(log_key, 'This is gonna be the log')
    if not r.exists(prog_key):
        r.lpush(prog_key, 'This is gonna be the progress')

    #i = 0
    #file = os.path.join(io_dirs['log'], "log.dat")
#
    #with open(file, 'a'):
    #    os.utime(file, None)
    #
    #with open(file) as file_:
    #    # Go to the end of file
    #    file_.seek(0,2)
    #    while run_pool:
    #        curr_position = file_.tell()
    #        line = file_.readline()
    #        if not line:
    #            file_.seek(curr_position)
    #            time.sleep(1)
    #        else:
    #            r.rpush('log', ("This is a log meessage from the service: current # " + line).encode('utf-8'))
    #            task.update_state(task_id=task_id, state='PROGRESS', meta={'process_percent': i})
    #            i = i + 1
    counter = 0
    while run_pool == True:
        r.rpush(log_key, ("This is a log meessage from the service: current # " + str(counter)).encode('utf-8'))
        r.rpush(prog_key, (str(counter)).encode('utf-8'))
        #task.update_state(task_id=task_id, state='PROGRESS', meta={'process_percent': counter})
        time.sleep(1)
        counter = counter + 1
    
    r.set(task_id, "done")
    
def start_container(task, task_id, docker_image_name, stage, io_env):
    global run_pool
    run_pool = True
    
    client = docker.from_env(version='auto')
   
    task.update_state(task_id=task_id, state='RUNNING')
    fut = pool.submit(_bg_job, task, task_id)

    client.containers.run(docker_image_name, "run", 
         detach=False, remove=True,
         volumes = {'workflow_input'  : {'bind' : '/input'}, 
                    'workflow_output' : {'bind' : '/output'},
                    'workflow_log'    : {'bind'  : '/log'}},
         environment=io_env)

    time.sleep(10)
    run_pool = False
    while not fut.done():
        time.sleep(0.1)

    # hash output
    output_hash = hash_job_output()

    store_job_output(output_hash)

   
    
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
