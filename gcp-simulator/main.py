import re
import time

from utils.resources import Latency, TS, Pagination
from typing import List

import dateutil.parser
import jwt
from fastapi import FastAPI, Query, Depends
from starlette.responses import Response
from utils.lib import *

(
    PROJECTS,
    SERVICES,
    SUB_PROJECTS,
    METRIC_TUPLES,
    INSTANCES,
    MIN_LATENCY,
    AVG_LATENCY,
    JITTER_MS,
) = get_env()

MT_MATCH = re.compile(r'metric\.type\s=\s"([^"]+?)"')

app = FastAPI()

ENABLED_APIS = {'cloudfunctions.googleapis.com', 'serviceruntime.googleapis.com', 'kubernetes.io',
                'monitoring.googleapis.com', 'cloudresourcemanager.googleapis.com'}

@app.get("/serviceusage.googleapis.com/v1/projects/{project_id}/services", dependencies=[Depends(Latency(MIN_LATENCY, JITTER_MS).delay)])
async def services(project_id: str, filter: str = "state:ENABLED", page: Pagination = Depends(Pagination(50).update)):
    if "DISABLED" in filter:
        return page.apply({"services": [{"config": {"name": f"disabled.service{s}.com"}} for s in range(SERVICES)] }, "services") # TODO: real responses (full-json)

    else:
        return page.apply({"services": [{"config": {"name": f"{s}"}} for s in ENABLED_APIS] }, "services")


@app.get('/cloudresourcemanager.googleapis.com/v1/projects', dependencies=[Depends(Latency(MIN_LATENCY, JITTER_MS).delay)])
async def projects(filter: str = "", pagination: Pagination = Depends(Pagination(50).update)):
    return pagination.apply({"projects": [{"projectId": f"fake-project-{i}"} for i in range(PROJECTS)]}, "projects") # TODO: real responses (full-json)


@app.get("/metadata.google.internal/computeMetadata/v1/instance/service-accounts/{account}/token", dependencies=[Depends(Latency(MIN_LATENCY, JITTER_MS).delay)])
async def get_token(account: str):
    return {"access_token": f"simulator-{account}-{int(time.time())}",
           "expires_in": 3000,
           "token_type": "Bearer"
            }


@app.get("/metadata.google.internal/computeMetadata/v1/instance/service-accounts/{account}/identity", dependencies=[Depends(Latency(MIN_LATENCY, JITTER_MS).delay)])
async def get_token(account: str):
    return Response(content=jwt.encode({'audience': 'simulator'}, "key", algorithm="HS256").encode("utf-8"), media_type="text/plain")


@app.get("/metadata.google.internal/computeMetadata/v1/{metadata:path}", dependencies=[Depends(Latency(MIN_LATENCY, JITTER_MS).delay)])
async def get_metadata(metadata: str):
    return Response(content=f"metadata:'{metadata}'", media_type="text/plain")

@app.get("/monitoring.googleapis.com/v3/projects/{project_id}/timeSeries", dependencies=[Depends(Latency(MIN_LATENCY, JITTER_MS).delay)])
async def time_series(project_id: str,
                            filter_str: str=Query(alias="filter"),
                            start_time:str=Query(alias="interval.startTime"),
                            end_time:str=Query(alias="interval.endTime"),
                            period=Query(alias="aggregation.alignmentPeriod"),
                            aligner=Query(alias="aggregation.perSeriesAligner"),
                            reducer=Query(alias="aggregation.crossSeriesReducer"),
                            group_by_fields: List[str]=Query(alias="aggregation.groupByFields"),
                            pagination=Depends(Pagination(100_000).update),
                       ):
    metric_type = MT_MATCH.search(filter_str).group(1)
    start = int(dateutil.parser.isoparse(start_time).timestamp())
    end = int(dateutil.parser.isoparse(end_time).timestamp())
    resolution = int(float(period[:-1]))

    resource_labels, metric_labels = find_labels(group_by_fields)

    requested_metric_tuples, metric_tuple, instance, sub_project, sample = calc_depth(
        METRIC_TUPLES,
        INSTANCES,
        SUB_PROJECTS,
        metric_labels,
        pagination,
        start,
        end,
        resolution,
    )

    limit = pagination.page_size

    ts_result_t = TS()
    for p in range(sub_project, SUB_PROJECTS):
        if limit <= 0:
            break

        for i in range(instance, INSTANCES):
            if limit <= 0:
                break

            res_dims = create_res_dims(resource_labels, project_id, SUB_PROJECTS, p, i)

            for t in range(metric_tuple, requested_metric_tuples):
                if limit <= 0:
                    break

                metric_t = create_metric(metric_labels, metric_type, t, res_dims)
                ts_result_t.timeSeries.append(metric_t)

                for s in range(sample*resolution+start, end, resolution):
                    if limit <= 0:
                        limit -= 1
                        break

                    point_t = create_point(s, p, i, resolution)
                    metric_t.points.append(point_t)

                    limit -= 1

    if limit == -1:
        ts_result_t.nextPageToken = "next-page-token-" + str(pagination.offset + pagination.page_size)

    return ts_result_t
