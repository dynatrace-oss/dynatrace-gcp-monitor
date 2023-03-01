from utils.resources import Point, Metric
import datetime

import os


def get_env():
    PROJECTS = int(os.environ.get("PROJECTS", "50"))
    SERVICES = int(os.environ.get("SERVICES", "3000"))
    SUB_PROJECTS = int(os.environ.get("SUB_PROJECTS", "1"))
    METRIC_TUPLES = int(os.environ.get("METRIC_TUPLES", "3"))
    INSTANCES = int(os.environ.get("INSTANCES", "50"))
    MIN_LATENCY = int(os.environ.get("MIN_LATENCY", "100"))
    AVG_LATENCY = int(os.environ.get("AVG_LATENCY", str(MIN_LATENCY + 10)))
    JITTER_MS = AVG_LATENCY - MIN_LATENCY

    return (
        PROJECTS,
        SERVICES,
        SUB_PROJECTS,
        METRIC_TUPLES,
        INSTANCES,
        MIN_LATENCY,
        AVG_LATENCY,
        JITTER_MS,
    )


def create_point(s, p, i, resolution):
    point_t = Point()

    point_t.interval.startTime = (
        datetime.datetime.fromtimestamp(s, datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    point_t.interval.endTime = (
        datetime.datetime.fromtimestamp(s + resolution, datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    point_t.value.int64Value = str(
        int(round(((s + p * 10000 + i) % (resolution * 5)) / (resolution * 5.0) * 100))
    )

    return point_t


def create_res_dims(resource_labels, project_id, sub_projects, p, i):
    res_dims = {}
    for rl in resource_labels:
        if rl.startswith("project"):
            res_dims[rl] = project_id + (f"-subproject-{p}" if sub_projects > 1 else "")
        else:
            res_dims[rl] = f"{rl}-instance-{i}"

        return res_dims


def create_metric(metric_labels, metric_type, t, res_dims):
    m_dims = {}
    for ml in metric_labels:
        m_dims[ml] = f"{ml}-{t}"

    metric_t = Metric()

    metric_t.metric.type = metric_type
    metric_t.metric.labels = m_dims

    metric_t.resource.type = metric_type
    metric_t.resource.labels = res_dims

    return metric_t


def calc_depth(
    metric_tuples,
    instances,
    sub_projects,
    metric_labels,
    pagination,
    start,
    end,
    resolution,
):
    samples = int((end - start) / resolution)
    requested_metric_tuples = metric_tuples if len(metric_labels) > 0 else 1
    offset = pagination.offset
    sample = int(offset / samples)
    offset /= samples
    metric_tuple = int(offset / requested_metric_tuples)
    offset /= requested_metric_tuples
    instance = int(offset % instances)
    offset /= instances
    sub_project = int(offset % sub_projects)

    return requested_metric_tuples, metric_tuple, instance, sub_project, sample


def find_labels(group_by_fields):
    resource_labels = set(
        map(
            lambda x: x.replace("resource.labels.", ""),
            filter(lambda x: x.startswith("resource.labels"), group_by_fields),
        )
    )
    metric_labels = set(
        map(
            lambda x: x.replace("metric.labels.", ""),
            filter(lambda x: x.startswith("metric.labels"), group_by_fields),
        )
    )

    return resource_labels, metric_labels
