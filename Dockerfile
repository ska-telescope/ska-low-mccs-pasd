FROM artefact.skao.int/ska-tango-images-pytango-builder:9.3.35 AS buildenv
FROM artefact.skao.int/ska-tango-images-pytango-runtime:9.3.22 AS runtime

USER root

RUN poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock* ./

RUN poetry install --only main

USER tango
