ARG PIP_VERSION=26.2.2

FROM python:3.12-slim AS build
ARG PIP_VERSION
RUN pip install --no-cache-dir --only-binary=:all: "pip==${PIP_VERSION}"
COPY src/requirements.txt .
# Hash-locked wheels only: no setup scripts run and no transitive dependency can drift between releases.
RUN pip install --no-cache-dir --only-binary=:all: --require-hashes --prefix=/install -r ./requirements.txt


FROM python:3.12-slim
ARG PIP_VERSION

# aiohttp verifies TLS against the system CA store, so take trust store fixes (such as CA distrusts)
# at build time instead of waiting for the base image to be rebuilt. Upgrading pip in place removes
# the base image's pip metadata, which scanners would otherwise report.
RUN apt-get update \
    && apt-get install -y --no-install-recommends --only-upgrade ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --only-binary=:all: "pip==${PIP_VERSION}"

ARG RELEASE_TAG_ARG
ENV RELEASE_TAG=$RELEASE_TAG_ARG

LABEL name="dynatrace-gcp-monitor" \
      vendor="Dynatrace LLC" \
      maintainer="Dynatrace Open Source" \
      version="1.x" \
      release="1" \
      url="https://github.com/dynatrace-oss/dynatrace-gcp-monitor/" \
      summary="Dynatrace function for Google Cloud Platform monitoring. This project is maintained by Dynatrace as Open Source Project." \
      description="Dynatrace function for Google Cloud Platform provides the mechanism to pull Google Cloud metrics and logs into Dynatrace."

WORKDIR /code
# Copy application dependencies only, not the build stage's pip installation.
COPY --from=build /install /usr/local
COPY src/ .
COPY LICENSE.md /licenses/

RUN adduser --disabled-password gcp-monitor && chown -R gcp-monitor /code
USER gcp-monitor

CMD [ "python", "-u", "./run_docker.py" ]
