FROM artefact.skao.int/ska-tango-images-pytango-builder:9.5.0 AS buildenv
FROM artefact.skao.int/ska-tango-images-pytango-runtime:9.5.0 AS runtime

USER root

ARG DEBIAN_FRONTEND=noninteractive

RUN apt update && apt install -y \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt update && apt install -y python3.11 python3.11-venv python3.11-dev \
    && python3.11 -m ensurepip --upgrade \
    && python3.11 -m pip install --upgrade pip \
    && apt clean

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1


RUN python3.11 -m pip install --upgrade pip poetry && \
    poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock* ./

RUN poetry install --only main

USER tango
