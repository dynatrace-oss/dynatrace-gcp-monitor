# -- Build stage: install Python dependencies --
FROM dhi.io/python:3.12-alpine3.23 AS build

RUN apk add --no-cache \
    build-base \
    libffi-dev \
    openssl-dev

RUN pip install --no-cache-dir --upgrade pip
COPY src/requirements.txt .
RUN pip install --no-cache-dir -r ./requirements.txt


# -- Runtime stage: hardened base image with zero known CVEs --
FROM dhi.io/python:3.12-alpine3.23

ARG RELEASE_TAG_ARG
ENV RELEASE_TAG=$RELEASE_TAG_ARG \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

LABEL name="dynatrace-gcp-monitor" \
      vendor="Dynatrace LLC" \
      maintainer="Dynatrace Open Source" \
      version="1.x" \
      release="1" \
      url="https://github.com/dynatrace-oss/dynatrace-gcp-monitor/" \
      summary="Dynatrace function for Google Cloud Platform monitoring. This project is maintained by Dynatrace as Open Source Project." \
      description="Dynatrace function for Google Cloud Platform provides the mechanism to pull Google Cloud metrics and logs into Dynatrace."

WORKDIR /code
COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY src/ .
COPY LICENSE.md /licenses/

RUN adduser -D -h /code gcp-monitor && chown -R gcp-monitor /code
USER gcp-monitor

CMD [ "python", "-u", "./run_docker.py" ]