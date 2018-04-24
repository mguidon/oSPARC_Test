import networkx as nx
from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base

from sqlalchemy_json import MutableJson


Base = declarative_base()

class ComputationalWorkflow(Base):
    __tablename__ = 'comp.workflow'

    id = Column(Integer, primary_key=True)
    dag_adjancency_list = Column(MutableJson)

    @property
    def execution_graph(self):
        d = self.dag_adjacency_list
        G = nx.DiGraph()

        for node in d.keys():
            nodes = d[node]
            if len(nodes) == 0:
                G.add_node(int(node))
                continue
            G.add_edges_from([(int(node), n) for n in nodes])
        return G

    def __repr__(self):
        return '<id {}>'.format(self.id)
