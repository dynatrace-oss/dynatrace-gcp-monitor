FROM python:3.9.17-slim-bullseye AS build
RUN apt-get update && apt-get install -y build-essential libffi-dev
RUN pip install --upgrade pip
COPY src/requirements.txt .
RUN pip install -r ./requirements.txt


FROM python:3.9.17-slim-bullseye

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
COPY --from=build /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages
COPY src/ .
COPY LICENSE.md /licenses/

RUN adduser --disabled-password gcp-monitor && chown -R gcp-monitor /code
USER gcp-monitor

CMD [ "python", "-u", "./run_docker.py" ]