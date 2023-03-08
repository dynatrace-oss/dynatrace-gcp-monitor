#!/bin/sh
export GCP_METADATA_URL='http://localhost:8080/metadata.google.internal/computeMetadata/v1'
export GCP_CLOUD_RESOURCE_MANAGER_URL='http://localhost:8080/cloudresourcemanager.googleapis.com/v1'
export GCP_SERVICE_USAGE_URL='http://localhost:8080/serviceusage.googleapis.com/v1'
export GCP_MONITORING_URL='http://localhost:8080/monitoring.googleapis.com/v3'

INSTANCES=2 PROJECTS=1 SUB_PROJECTS=200 python -m uvicorn main:app  --host 0.0.0.0 --port 8080 --no-access-log & python ../src/dev_local_run.py
