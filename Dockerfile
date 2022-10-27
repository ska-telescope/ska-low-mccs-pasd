FROM artefact.skao.int/ska-tango-images-pytango-builder:9.3.32 AS buildenv
FROM artefact.skao.int/ska-tango-images-pytango-runtime:9.3.19 AS runtime

# create ipython profile to so that itango doesn't fail if ipython hasn't run yet
#RUN ipython profile create

USER root

RUN python3 -m pip install poetry
RUN poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock* ./

RUN poetry install --only main

USER tango
