#!/bin/sh
INSTANCES=2 PROJECTS=2 SUB_PROJECTS=200 python -m uvicorn main:app  --host 0.0.0.0 --port 8080
