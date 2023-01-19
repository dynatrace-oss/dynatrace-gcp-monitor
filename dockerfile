FROM python:3.8-slim-buster AS build
RUN apt-get update && apt-get install -y build-essential libffi-dev
RUN pip install --upgrade pip
COPY src/requirements.txt .
RUN pip install -r ./requirements.txt


FROM python:3.8-slim-buster

ARG VERSION_TAG_ARG
ENV VERSION_TAG=$VERSION_TAG_ARG

LABEL name="dynatrace-gcp-function" \
      vendor="Dynatrace LLC" \
      maintainer="Dynatrace Open Source" \
      version="1.x" \
      release="1" \
      url="https://github.com/dynatrace-oss/dynatrace-gcp-function/" \
      summary="Dynatrace function for Google Cloud Platform monitoring. This project is maintained by Dynatrace as Open Source Project." \
      description="Dynatrace function for Google Cloud Platform provides the mechanism to pull Google Cloud metrics and logs into Dynatrace."

WORKDIR /code
COPY --from=build /usr/local/lib/python3.8/site-packages /usr/local/lib/python3.8/site-packages
COPY src/ .
COPY LICENSE.md /licenses/
CMD [ "python", "-u", "./run_docker.py" ]