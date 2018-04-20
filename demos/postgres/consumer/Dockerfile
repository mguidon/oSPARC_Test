FROM continuumio/miniconda3
LABEL maintainer="Manuel Guidon <guidon@itis.ethz.ch>"

RUN conda install flask sqlalchemy psycopg2
RUN pip install pgpubsub

EXPOSE 8012

WORKDIR /work

CMD ["python", "consumer.py"]
