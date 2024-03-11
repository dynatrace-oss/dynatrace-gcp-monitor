import os


def get_int_environment_value(key: str, default_value: int) -> int:
    environment_value = os.environ.get(key, None)
    return int(environment_value) if environment_value and environment_value.isdigit() else default_value


def operation_mode():
    return os.environ.get("OPERATION_MODE", None)


def activation_config():
    return os.environ.get("ACTIVATION_CONFIG", "")


def self_monitoring_enabled():
    return os.environ.get('SELF_MONITORING_ENABLED', "FALSE").upper() in ["TRUE", "YES"]


def print_metric_ingest_input():
    return os.environ.get("PRINT_METRIC_INGEST_INPUT", "FALSE").upper() in ["TRUE", "YES"]


def metric_autodiscovery():
    return os.environ.get("METRIC_AUTODISCOVERY","FALSE").upper() in ["TRUE", "YES"]


def scoping_project_support_enabled():
    return os.environ.get("SCOPING_PROJECT_SUPPORT_ENABLED", "FALSE").upper() in ["TRUE", "YES"]


def query_interval_min():
    return os.environ.get('QUERY_INTERVAL_MIN', None)


def excluded_projects():
    return os.environ.get("EXCLUDED_PROJECTS", "")


def excluded_projects_by_prefix():
    return os.environ.get("EXCLUDED_PROJECTS_BY_PREFIX", "")


def project_id():
    return os.environ.get("GCP_PROJECT","")


def credentials_path():
    return os.environ['GOOGLE_APPLICATION_CREDENTIALS'] if 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ.keys() else ""


def dynatrace_access_key_secret_name():
    return os.environ.get("DYNATRACE_ACCESS_KEY_SECRET_NAME", None)


def dynatrace_url_secret_name():
    return os.environ.get("DYNATRACE_URL_SECRET_NAME", None)


def dynatrace_log_ingest_url_secret_name():
    return os.environ.get("DYNATRACE_LOG_INGEST_URL_SECRET_NAME", None)


def keep_refreshing_extensions_config():
    return os.environ.get("KEEP_REFRESHING_EXTENSIONS_CONFIG", "TRUE").upper() in ["TRUE", "YES"]


def release_tag():
    return os.environ.get("RELEASE_TAG", "version value not provided")


def gcp_metadata_url():
    return os.environ.get('GCP_METADATA_URL', 'http://metadata.google.internal/computeMetadata/v1')


def gcp_cloud_resource_manager_url():
    return os.environ.get('GCP_CLOUD_RESOURCE_MANAGER_URL', 'https://cloudresourcemanager.googleapis.com/v1')


def gcp_service_usage_url():
    return os.environ.get("GCP_SERVICE_USAGE_URL", "https://serviceusage.googleapis.com/v1")


def gcp_monitoring_url():
    return os.environ.get("GCP_MONITORING_URL", "https://monitoring.googleapis.com/v3")

def gcp_allowed_metric_dimension_value_length():
    return get_int_environment_value("ALLOWED_METRIC_DIMENSION_VALUE_LENGTH", 250)


def gcp_allowed_metric_dimension_key_length():
    return get_int_environment_value("ALLOWED_METRIC_DIMENSION_KEY_LENGTH", 100)


def gcp_allowed_metric_key_length():
    return get_int_environment_value("ALLOWED_METRIC_KEY_LENGTH", 250)


def gcp_allowed_metric_display_name():
    return get_int_environment_value("ALLOWED_METRIC_DISPLAY_NAME_LENGTH", 300)


def gcp_allowed_metric_description():
    return get_int_environment_value("ALLOWED_METRIC_DESCRIPTION_LENGTH", 65535)


def gcp_allowed_metric_unit_name():
    return get_int_environment_value("ALLOWED_METRIC_UNIT_NAME_LENGTH", 63)


def get_autodiscovery_querry_interval():
    return get_int_environment_value("AUTODISCOVERY_QUERY_INTERVAL", 60)

def gcp_autodiscovery_include_alpha_metrics():
    return os.environ.get("AUTODISCOVERY_INCLUDE_ALPHA_METRICS", "TRUE").upper() in ["TRUE", "YES","Y"]

def max_dimension_name_length():
    return get_int_environment_value("MAX_DIMENSION_NAME_LENGTH", 100)


def max_dimension_value_length():
    return get_int_environment_value("MAX_DIMENSION_VALUE_LENGTH", 250)


def get_dynatrace_api_key_from_env():
    return os.environ.get("DYNATRACE_ACCESS_KEY", None)

def get_dynatrace_url_from_env():
    return os.environ.get("DYNATRACE_URL", None)

def get_dynatrace_log_ingest_url_from_env():
    return os.environ.get("DYNATRACE_LOG_INGEST_URL", None)


def use_proxy():
    return os.environ.get("USE_PROXY", "").upper()


def require_valid_certificate():
    return os.environ.get("REQUIRE_VALID_CERTIFICATE", "TRUE").upper() in ["TRUE", "YES"]


def hostname():
    return os.environ.get("HOSTNAME", "")
