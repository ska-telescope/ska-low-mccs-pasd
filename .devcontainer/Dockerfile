FROM artefact.skao.int/ska-tango-images-pytango-builder:9.5.0 AS buildenv

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    gnupg2 openssh-client software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && apt-get install -y \
    python3.11 python3.11-venv python3.11-dev && \
    python3.11 -m ensurepip --upgrade && \
    python3.11 -m pip install --upgrade pip && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 && \
    apt-get clean

RUN poetry self update -n 1.8.4
