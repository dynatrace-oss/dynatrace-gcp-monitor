FROM python:alpine

WORKDIR /code

COPY src/ .

RUN apk add build-base libffi-dev

RUN pip install -r requirements.txt

CMD [ "python", "./run_docker.py" ]