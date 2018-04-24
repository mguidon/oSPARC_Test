FROM continuumio/miniconda3
LABEL maintainer="Manuel Guidon <guidon@itis.ethz.ch>"

RUN conda install flask sqlalchemy psycopg2 networkx
RUN pip install sqlalchemy-json

EXPOSE 8010

WORKDIR /work

CMD ["python", "client.py"]
