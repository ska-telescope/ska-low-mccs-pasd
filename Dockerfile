FROM artefact.skao.int/ska-tango-images-pytango-builder:9.4.3 AS buildenv
FROM artefact.skao.int/ska-tango-images-pytango-runtime:9.4.3 AS runtime

USER root

RUN poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock* ./

RUN poetry install --only main

USER tango
