FROM artefact.skao.int/ska-tango-images-pytango-builder:9.5.0 AS buildenv
FROM artefact.skao.int/ska-tango-images-pytango-runtime:9.5.0 AS runtime

USER root

ARG DEBIAN_FRONTEND=noninteractive

RUN apt update && apt install -y \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt install -y python3.11 python3.11-venv \
    && python3.11 -m ensurepip \
    && python3.11 -m pip install --upgrade pip poetry \
    && poetry config virtualenvs.create false \
    && apt clean

COPY pyproject.toml poetry.lock* ./

RUN poetry install --only main

USER tango
