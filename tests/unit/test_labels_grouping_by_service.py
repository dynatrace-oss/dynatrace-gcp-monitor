from lib.autodiscovery.models import AutodiscoveryResourceLinking
from lib.metrics import AutodiscoveryGCPService, GCPService, Metric
from lib.utilities import NO_GROUPING_CATEGORY, read_labels_grouping_by_service_yaml


def _create_metric(google_metric: str, autodiscovered_metric: bool = False) -> Metric:
    return Metric(
        key="cloud.gcp.test.metric.gauge",
        value=f"metric:{google_metric}",
        type="gauge",
        dimensions=[],
        autodiscovered_metric=autodiscovered_metric,
        gcpOptions={
            "valueType": "INT64",
            "metricKind": "GAUGE",
            "samplePeriod": 60,
            "ingestDelay": 60,
        },
    )


def _create_service(name: str, autodiscovery_enabled: bool = False) -> GCPService:
    return GCPService(
        service=name,
        featureSet="default",
        extension_name="dynatrace.test",
        autodiscovery_enabled=autodiscovery_enabled,
    )


def _set_groupings(service, configured_services_to_group, metric=None,
                   group_all_services_by_user_label=""):
    service_name = service.name
    if (
        metric
        and metric.autodiscovered_metric
        and isinstance(service, AutodiscoveryGCPService)
    ):
        linked = service.metrics_to_linking.get(metric.google_metric)
        if linked and linked.possible_service_linking:
            service_name = linked.possible_service_linking[0].name
        else:
            service_name = service.metrics_to_resources.get(metric.google_metric)

    groupings = []
    for configured_service_to_group in configured_services_to_group:
        if configured_service_to_group.get("service") == service_name:
            for configured_grouping in configured_service_to_group.get("groupings"):
                groupings.append(configured_grouping)
    if not groupings and group_all_services_by_user_label:
        groupings.append(group_all_services_by_user_label)
    if not groupings:
        groupings.append(NO_GROUPING_CATEGORY)

    return groupings


def test_regular_service_groupings_use_service_name():
    service = _create_service("cloudsql_database")
    metric = _create_metric("cloudsql.googleapis.com/database/cpu/utilization")
    configured_services_to_group = [
        {"service": "cloudsql_database", "groupings": {"user_label_1,user_label_2"}}
    ]

    assert _set_groupings(service, configured_services_to_group, metric) == [
        "user_label_1,user_label_2"
    ]


def test_linked_autodiscovery_metric_uses_linked_service_name():
    linked_service = _create_service("cloudsql_database", autodiscovery_enabled=True)
    metric = _create_metric(
        "cloudsql.googleapis.com/database/cpu/utilization",
        autodiscovered_metric=True,
    )
    autodiscovery_service = AutodiscoveryGCPService()
    autodiscovery_service.set_metrics(
        {"cloudsql_database": [metric]},
        {"cloudsql_database": AutodiscoveryResourceLinking([linked_service], [])},
        {},
    )
    configured_services_to_group = [
        {"service": "cloudsql_database", "groupings": {"user_label_1,user_label_2"}}
    ]

    assert _set_groupings(
        autodiscovery_service, configured_services_to_group, metric
    ) == ["user_label_1,user_label_2"]


def test_unlinked_autodiscovery_metric_falls_back_to_no_grouping():
    metric = _create_metric(
        "redis.googleapis.com/cluster/memory/average_utilization",
        autodiscovered_metric=True,
    )
    autodiscovery_service = AutodiscoveryGCPService()
    autodiscovery_service.set_metrics(
        {"redis_cluster": [metric]},
        {"redis_cluster": None},
        {},
    )
    configured_services_to_group = [
        {"service": "cloudsql_database", "groupings": {"user_label_1,user_label_2"}}
    ]

    assert _set_groupings(
        autodiscovery_service, configured_services_to_group, metric
    ) == [NO_GROUPING_CATEGORY]


def test_standalone_autodiscovery_metric_uses_resource_name():
    metric = _create_metric(
        "redis.googleapis.com/cluster/memory/average_utilization",
        autodiscovered_metric=True,
    )
    autodiscovery_service = AutodiscoveryGCPService()
    autodiscovery_service.set_metrics(
        {"redis_cluster": [metric]},
        {"redis_cluster": None},
        {},
    )
    configured_services_to_group = [
        {"service": "redis_cluster", "groupings": {"env,team"}}
    ]

    assert _set_groupings(
        autodiscovery_service, configured_services_to_group, metric
    ) == ["env,team"]


def test_multiple_groupings_are_preserved_for_linked_service():
    configured_services_to_group = [
        {
            "service": "cloudsql_database",
            "groupings": {"user_label_1,user_label_2", "user_label_3"},
        }
    ]
    service = _create_service("cloudsql_database")
    metric = _create_metric("cloudsql.googleapis.com/database/cpu/utilization")

    groupings = _set_groupings(service, configured_services_to_group, metric)

    assert set(groupings) == {"user_label_1,user_label_2", "user_label_3"}


def test_unknown_service_falls_back_to_no_grouping():
    configured_services_to_group = [
        {"service": "cloudsql_database", "groupings": {"user_label_1,user_label_2"}}
    ]
    service = _create_service("pubsub_subscription")
    metric = _create_metric("pubsub.googleapis.com/subscription/ack_latencies")

    groupings = _set_groupings(service, configured_services_to_group, metric)

    assert groupings == [NO_GROUPING_CATEGORY]


# --- GROUP_ALL_SERVICES_BY_USER_LABEL ---

def test_global_label_groups_a_service_with_no_explicit_grouping():
    service = _create_service("pubsub_subscription")
    metric = _create_metric("pubsub.googleapis.com/subscription/num_undelivered_messages")

    assert _set_groupings(
        service, [], metric, group_all_services_by_user_label="example_label"
    ) == ["example_label"]


def test_explicit_grouping_wins_over_the_global_label():
    service = _create_service("cloudsql_database")
    metric = _create_metric("cloudsql.googleapis.com/database/cpu/utilization")
    configured_services_to_group = [
        {"service": "cloudsql_database", "groupings": {"user_label_1,user_label_2"}}
    ]

    assert _set_groupings(
        service, configured_services_to_group, metric,
        group_all_services_by_user_label="example_label",
    ) == ["user_label_1,user_label_2"]


def test_no_global_label_falls_back_to_no_grouping():
    service = _create_service("pubsub_subscription")
    metric = _create_metric("pubsub.googleapis.com/subscription/num_undelivered_messages")

    assert _set_groupings(service, [], metric) == [NO_GROUPING_CATEGORY]


# --- One query per service: several groupings are collapsed into one ---

def _read_groupings(monkeypatch, yaml_text):
    monkeypatch.setenv("LABELS_GROUPING_BY_SERVICE", yaml_text)
    return {s["service"]: s["groupings"] for s in read_labels_grouping_by_service_yaml()}


def test_single_comma_separated_grouping_is_left_alone(monkeypatch):
    groupings = _read_groupings(monkeypatch, """
services:
- service: cloudsql_database
  groupings:
    - stage,owner
""")

    assert groupings["cloudsql_database"] == {"stage,owner"}


def test_several_groupings_are_merged_into_one(monkeypatch):
    # Two groupings would be two queries, ingesting every matching resource twice.
    groupings = _read_groupings(monkeypatch, """
services:
- service: cloudsql_database
  groupings:
    - stage,owner
    - example_label
""")

    assert groupings["cloudsql_database"] == {"stage,owner,example_label"}


def test_labels_repeated_across_groupings_are_deduplicated(monkeypatch):
    groupings = _read_groupings(monkeypatch, """
services:
- service: cloudsql_database
  groupings:
    - stage,owner
    - owner,example_label
""")

    assert groupings["cloudsql_database"] == {"stage,owner,example_label"}


def test_whitespace_around_labels_is_stripped(monkeypatch):
    groupings = _read_groupings(monkeypatch, """
services:
- service: cloudsql_database
  groupings:
    - " stage , owner "
""")

    assert groupings["cloudsql_database"] == {"stage,owner"}


def test_service_without_groupings_yields_none(monkeypatch):
    groupings = _read_groupings(monkeypatch, """
services:
- service: cloudsql_database
  groupings: []
""")

    assert groupings["cloudsql_database"] == set()
