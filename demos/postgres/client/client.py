from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
import uuid
import time
from models import ComputationalWorkflow, ComputationalTask, Base, UNKNOWN, PENDING, RUNNING, SUCCESS, FAILED

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


app = Flask(__name__)

DB_URL = 'postgresql+psycopg2://{user}:{pw}@{url}/{db}'.format(user=POSTGRES_USER,pw=POSTGRES_PW,url=POSTGRES_URL,db=POSTGRES_DB)

db = create_engine(DB_URL, client_encoding='utf8')

Session = sessionmaker(db)
session = Session()

Base.metadata.create_all(db)

def _find_entry_points(G):
    result = []
    for node in G.nodes:
        if len(list(G.predecessors(node))) == 0:
            result.append(node)
    return result

def _is_node_ready(task, graph):
    tasks = session.query(ComputationalTask).filter(ComputationalTask.node_id.in_(list(graph.predecessors(task.node_id)))).all()
    for dep_task in tasks:
        if not dep_task.job_id or not dep_task.state == SUCCESS:
            return False
    return True

def _process_task_node(task):
    task.job_id = str(uuid.uuid4())
    task.state = RUNNING
    session.commit()
    time.sleep(5)
    session.commit()
    task.state = SUCCESS
    session.commit()


def _next(workflow_id, node_id=None):
    workflow = session.query(ComputationalWorkflow).filter_by(workflow_id=workflow_id).one()
    graph = workflow.execution_graph
    next_task_nodes = []
    if node_id:
        task = session.query(ComputationalTask).filter_by(node_id=node_id).one()
        # already done and happy
        if not task.job_id and task.state is SUCCESS:
            return
        # not yet ready because predecessors are not
        if not _is_node_ready(task, graph):
            return

        _process_task_node(task)
        next_task_nodes = list(graph.successors(node_id))
    else:
        next_task_nodes = _find_entry_points(graph)

    
    for node_id in next_task_nodes:
        _next(workflow_id, node_id)


@app.route('/')
def hello():
    return "Hello World!"


@app.route('/drop_all')
def drop_all():
    Base.metadata.drop_all(db)
    Base.metadata.create_all(db)
    return "DB tables delete and recreated"

@app.route('/next/<int:workflow_id>')
def next(workflow_id):
    _next(workflow_id)

    return "Done"

@app.route('/add')
def hello_name():
    node_ids = []
    for i in range(8):
        node_ids.append(str(uuid.uuid4()))

    dag_adjacency_list = dict()
    dag_adjacency_list[node_ids[0]] = [node_ids[2]]
    dag_adjacency_list[node_ids[1]] = [node_ids[3]]
    dag_adjacency_list[node_ids[2]] = [node_ids[4]]
    dag_adjacency_list[node_ids[3]] = [node_ids[4]]
    dag_adjacency_list[node_ids[4]] = [node_ids[5], node_ids[6]]
    dag_adjacency_list[node_ids[5]] = [node_ids[7]]
    dag_adjacency_list[node_ids[6]] = [node_ids[7]]


    new_cw = ComputationalWorkflow(dag_adjacency_list = dag_adjacency_list,
    state=0)

    session.add(new_cw)
    session.flush()

    workflow_id = new_cw.workflow_id

    for node_id in node_ids:
        new_task = ComputationalTask(workflow_id=workflow_id, node_id=node_id)
        session.add(new_task)

    session.commit()

    return "Added new workflow {}".format(workflow_id)


if __name__ == '__main__':
    app.run(port=8010, debug=True, host='0.0.0.0', threaded=True)