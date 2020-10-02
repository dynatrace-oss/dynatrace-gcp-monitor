FROM python:3.8-slim-buster AS build
RUN apt-get update && apt-get install -y build-essential libffi-dev
RUN pip install --upgrade pip
COPY src/requirements.txt .
RUN pip install -r ./requirements.txt

FROM python:3.8-slim-buster
WORKDIR /code
COPY --from=build /usr/local/lib/python3.8/site-packages /usr/local/lib/python3.8/site-packages
COPY src/ .
CMD [ "python", "./run_docker.py" ]