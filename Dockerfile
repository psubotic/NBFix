# syntax=docker/dockerfile:1

# ---- build stage: has Python + Node, builds nbcore + NBHarness + the JupyterLab labextension into a venv ----
FROM python:3.11-slim AS build

# Node.js is only needed here to build jupyterlab-nbharness's TypeScript
# source into static assets - it never ends up in the runtime image below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /src
# nbcore and nbharness are separate installable packages (see each
# directory's own pyproject.toml) - nbharness declares nbcore as a
# dependency, but since nbcore isn't published anywhere, both local
# paths must be passed to the same pip install so the resolver can
# satisfy that dependency from the local copy instead of failing to
# find "nbcore" on an index. jupyter-config/ now lives inside
# nbharness/ and installs automatically via its own pyproject.toml
# shared-data config - no separate COPY needed for it.
COPY nbcore ./nbcore
COPY nbharness ./nbharness
COPY jupyterlab-nbharness ./jupyterlab-nbharness

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ./nbcore "./nbharness[jupyter]" "jupyterlab>=4,<5" \
    && pip install --no-cache-dir ./jupyterlab-nbharness

# ---- runtime stage: slim, no Node/npm/node_modules/build toolchain ----
FROM python:3.11-slim AS runtime

RUN useradd --create-home --shell /bin/bash nbharness
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

USER nbharness
WORKDIR /home/nbharness/work
EXPOSE 8888

# No token/password is baked in here on purpose - JupyterLab generates a
# fresh one at startup and prints the URL (with token) to the container
# logs. Run `docker logs <container>` to get the link to open.
CMD ["jupyter", "lab", "--ip=0.0.0.0", "--port=8888", "--no-browser"]
