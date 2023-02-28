#!/bin/sh
export DEV_URL='http://localhost:8080'

INSTANCES=2 PROJECTS=1 SUB_PROJECTS=200 python -m uvicorn main:app  --host 0.0.0.0 --port 8080 & python ../src/dev_local_run.py