# GCP SIMULATOR

Simulates a couple of GCP endpoints. Uses **FastAPI** framework with **uvicorn** server:
  * `metadata.google.internal/computeMetadata/v1/`
  * `monitoring.googleapis.com/v3/projects/{project_id}/timeSeries`
  * `cloudresourcemanager.googleapis.com/v1/projects`
  * `serviceusage.googleapis.com/v1/projects/{project_id}/services`

## Environment variables (with defaults)
  * `MIN_LATENCY = 20` - minimal latency in *ms*
  * `AVG_LATENCY = MIN_LATENCY + 10` - mean latency in *ms* (gamma distribution: alpha = 1, beta = 0.5)
  * `SERVICES = 3000` - number of **available** services
  * `PROJECTS = 50` - number of accessible projects
  * `SUB_PROJECTS = 1` - number of projects per one monitoring project in __scope metrics__ mode, use `1` to disable  __scope metrics__
  * `INSTANCES = 50` - number of `metric.labels` tuples to generate per sub-project/project
  * `METRIC_TUPLES = 3` - number of `metric.labels` tuples to generate per resource

Total number of timeseries = PROJECTS * SUB_PROJECTS * INSTANCES * METRIC_TUPLES(if requested)
Number of datapoints = Total number of timeseries * ( Requested timespan / Requested resolution )         
## run project
  pip install -r requirements.txt
  ./run.sh

## Usage example
  PROJECTS=100 INSTANCES=1000 SUB_PROJECTS=200 python -m uvicorn main:app --host 0.0.0.0 --port 8080
