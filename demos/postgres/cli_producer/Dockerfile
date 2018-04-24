FROM continuumio/miniconda3
LABEL maintainer="Manuel Guidon <guidon@itis.ethz.ch>"

RUN conda install flask sqlalchemy psycopg2
RUN pip install pgpubsub

WORKDIR /work

CMD ["python", "cli_producer.py"]
