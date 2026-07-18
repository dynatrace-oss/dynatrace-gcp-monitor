import asyncio
from datetime import datetime
from unittest import mock

from lib.context import MetricsContext
from lib.entities.extractors import gce_instance
from lib.metrics import GCPService


def _metrics_context() -> MetricsContext:
    return MetricsContext(None, None, "", "", datetime.utcnow(), 0, "", "", False, False, None)


@mock.patch("lib.entities.extractors.gce_instance.generic_paging", new_callable=mock.AsyncMock)
@mock.patch("lib.entities.extractors.gce_instance.fetch_zones", new_callable=mock.AsyncMock)
def test_get_gce_instance_entity_skips_failed_zone(mock_fetch_zones, mock_generic_paging):
    ctx = _metrics_context()
    entities = [mock.MagicMock()]

    mock_fetch_zones.return_value = ["zone-a", "zone-b"]
    mock_generic_paging.side_effect = [entities, ConnectionError("zone-b failed")]

    svc_def = GCPService(service="gce_instance")

    result = asyncio.run(gce_instance.get_gce_instance_entity(ctx, "my_project", svc_def))

    assert list(result) == entities
