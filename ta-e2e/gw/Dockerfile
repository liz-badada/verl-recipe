# Gateway-only image for the end-to-end run: uni-agent's CI dependency set (python 3.12,
# requirements-test.txt, its verl submodule) without SWE-bench. The repos are bind-mounted
# at run time, so the gateway serves the live verl-recipe branch against unmodified uni-agent.
FROM python:3.12-slim
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential curl && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
COPY requirements-test.txt /workspace/requirements-test.txt
COPY verl /workspace/verl
RUN python -m pip install --upgrade pip && pip install -r requirements-test.txt
ENV PYTHONPATH=/workspace
