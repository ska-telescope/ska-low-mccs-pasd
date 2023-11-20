FROM registry.gitlab.com/ska-telescope/ska-tango-images/ska-tango-images-pytango-builder:c863a168 AS buildenv
FROM registry.gitlab.com/ska-telescope/ska-tango-images/ska-tango-images-pytango-runtime:c863a168 AS runtime

USER root

RUN poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock* ./

RUN poetry install --only main

USER tango
