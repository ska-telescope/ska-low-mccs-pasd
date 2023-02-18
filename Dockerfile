FROM artefact.skao.int/ska-tango-images-pytango-builder:9.3.35 AS buildenv
FROM artefact.skao.int/ska-tango-images-pytango-runtime:9.3.22 AS runtime

USER root

# Temporary, just while we're depending on unreleased ska-low-mccs-common main branch.
# Please don't let me merge this!
RUN apt-get update && apt-get install -y git

RUN poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock* ./

RUN poetry install --only main

USER tango
