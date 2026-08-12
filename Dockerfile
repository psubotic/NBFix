# syntax=docker/dockerfile:1

# ---- build stage: has Python + Node, builds nbsynth + the JupyterLab labextension into a venv ----
FROM python:3.11-slim AS build

# Node.js is only needed here to build jupyterlab-nbsynth's TypeScript
# source into static assets - it never ends up in the runtime image below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /src
COPY pyproject.toml README.md ./
COPY src ./src
COPY jupyter-config ./jupyter-config
COPY jupyterlab-nbsynth ./jupyterlab-nbsynth

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[jupyter]" "jupyterlab>=4,<5" \
    && pip install --no-cache-dir ./jupyterlab-nbsynth

# ---- runtime stage: slim, no Node/npm/node_modules/build toolchain ----
FROM python:3.11-slim AS runtime

RUN useradd --create-home --shell /bin/bash nbsynth
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

USER nbsynth
WORKDIR /home/nbsynth/work
EXPOSE 8888

# No token/password is baked in here on purpose - JupyterLab generates a
# fresh one at startup and prints the URL (with token) to the container
# logs. Run `docker logs <container>` to get the link to open.
CMD ["jupyter", "lab", "--ip=0.0.0.0", "--port=8888", "--no-browser"]
