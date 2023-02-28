import os


def self_monitoring_enabled():
    return os.environ.get('SELF_MONITORING_ENABLED', "FALSE").upper() in ["TRUE", "YES"]


def print_metric_ingest_input():
    return os.environ.get("PRINT_METRIC_INGEST_INPUT", "FALSE").upper() in ["TRUE", "YES"]


def scoping_project_support_enabled():
    return os.environ.get("SCOPING_PROJECT_SUPPORT_ENABLED", "FALSE").upper() in ["TRUE", "YES"]


def project_id():
    return os.environ.get("GCP_PROJECT")


def credentials_path():
    return os.environ['GOOGLE_APPLICATION_CREDENTIALS'] if 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ.keys() else ""


def dynatrace_access_key_secret_name():
    return os.environ.get("DYNATRACE_ACCESS_KEY_SECRET_NAME", "DYNATRACE_ACCESS_KEY")


def dynatrace_url_secret_name():
    return os.environ.get("DYNATRACE_URL_SECRET_NAME", "DYNATRACE_URL")


def dynatrace_log_ingest_url_secret_name():
    return os.environ.get("DYNATRACE_LOG_INGEST_URL_SECRET_NAME", "DYNATRACE_LOG_INGEST_URL")


def keep_refreshing_extensions_config():
    return os.environ.get("KEEP_REFRESHING_EXTENSIONS_CONFIG", "TRUE").upper() in ["TRUE", "YES"]


def release_tag():
    return os.environ.get("RELEASE_TAG", "version value not provided")


def gcp_metadata_url():
    DEV_URL = os.environ.get("DEV_URL", None)
    if DEV_URL:
        return "http://localhost:8080/metadata.google.internal/computeMetadata/v1"

    return os.environ.get('GCP_METADATA_URL', 'http://metadata.google.internal/computeMetadata/v1')


def gcp_cloud_resource_manager_url():
    DEV_URL = os.environ.get("DEV_URL", None)
    if DEV_URL:
        return "http://localhost:8080/cloudresourcemanager.googleapis.com/v1"

    return os.environ.get('GCP_CLOUD_RESOURCE_MANAGER_URL', 'https://cloudresourcemanager.googleapis.com/v1')


def gcp_service_usage_url():
    DEV_URL = os.environ.get("DEV_URL", None)
    if DEV_URL:
        return "http://localhost:8080/serviceusage.googleapis.com/v1"

    return os.environ.get("GCP_SERVICE_USAGE_URL", "https://serviceusage.googleapis.com/v1")


def gcp_monitoring_url():
    DEV_URL = os.environ.get("DEV_URL", None)
    if DEV_URL:
        return  "http://localhost:8080/monitoring.googleapis.com/v3"
    
    return os.environ.get("GCP_MONITORING_URL", "https://monitoring.googleapis.com/v3")
