FROM artefact.skao.int/ska-tango-images-pytango-builder:9.3.35 AS buildenv
FROM artefact.skao.int/ska-tango-images-pytango-runtime:9.3.22 AS runtime

USER root

RUN poetry config virtualenvs.create false
RUN apt-get update && apt-get install -y \
    libcap2-bin \
    sudo \
    python3.10
COPY pyproject.toml poetry.lock* ./

RUN poetry install --only main
RUN setcap cap_net_raw,cap_ipc_lock,cap_sys_nice,cap_sys_admin,cap_kill+ep /usr/bin/python3.10
USER tango
