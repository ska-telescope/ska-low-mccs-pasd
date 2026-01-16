FROM artefact.skao.int/ska-tango-images-tango-dsconfig:1.8.3 AS tools
FROM artefact.skao.int/ska-python:0.2.5 AS runtime

WORKDIR /app

COPY --from=tools /usr/local/bin/retry /usr/local/bin/retry
COPY --from=tools /usr/local/bin/wait-for-it.sh /usr/local/bin/wait-for-it.sh

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./

# Install Git executable - only needed when pulling dev branches
RUN apt-get update && apt-get install -y --no-install-recommends git

RUN --mount=from=ghcr.io/astral-sh/uv,source=/uv,target=/bin/uv \
    uv sync --locked --no-install-project --no-dev

COPY . .

RUN --mount=from=ghcr.io/astral-sh/uv,source=/uv,target=/bin/uv \
    uv sync --locked --no-dev
