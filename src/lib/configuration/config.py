import os


def self_monitoring_enabled():
    return os.environ.get('SELF_MONITORING_ENABLED', "FALSE").upper() in ["TRUE", "YES"]


def print_metric_ingest_input():
    return os.environ.get("PRINT_METRIC_INGEST_INPUT", "FALSE").upper() in ["TRUE", "YES"]


def scoping_project_support_enabled():
    return os.environ.get("SCOPING_PROJECT_SUPPORT_ENABLED", "FALSE").upper() in ["TRUE", "YES"]


def project_id():
    return os.environ.get("GCP_PROJECT")
