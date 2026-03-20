from lib.autodiscovery.models import AutodiscoveryResourceLinking
from lib.metrics import AutodiscoveryGCPService, GCPService, Metric
from lib.utilities import NO_GROUPING_CATEGORY


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


def _set_groupings(service, configured_services_to_group, metric=None):
    service_name = service.name
    if (
        metric
        and metric.autodiscovered_metric
        and isinstance(service, AutodiscoveryGCPService)
    ):
        linked = service.metrics_to_linking.get(metric.google_metric)
        service_name = (
            linked.possible_service_linking[0].name
            if linked and linked.possible_service_linking
            else None
        )

    groupings = []
    for configured_service_to_group in configured_services_to_group:
        if configured_service_to_group.get("service") == service_name:
            for configured_grouping in configured_service_to_group.get("groupings"):
                groupings.append(configured_grouping)
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
