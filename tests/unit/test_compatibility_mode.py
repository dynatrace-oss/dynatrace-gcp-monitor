#   Copyright 2021 Dynatrace LLC
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
from typing import NewType, Any

from lib.context import LoggingContext
from main import load_supported_services

context = LoggingContext("TEST")
MonkeyPatchFixture = NewType("MonkeyPatchFixture", Any)

def test_dimension_loading_config_compatibility_mode_false(monkeypatch: MonkeyPatchFixture):
    monkeypatch.setenv("COMPATIBILITY_MODE", "False")

    config = load_supported_services(context, [])

    assert len(config) == 87

    all_loaded_dt_dimensions = all_loaded_dt_dimension_labels(config)

    # new should be present
    assert "gcp.project.id" in all_loaded_dt_dimensions
    assert "gcp.region" in all_loaded_dt_dimensions
    assert "gcp.instance.name" in all_loaded_dt_dimensions

    # old should not be present - compatibilityMode off
    assert "project_id" not in all_loaded_dt_dimensions
    # assert "region" not in all_loaded_dt_dimensions #region can be sometimes present when there's both region & zone in one config: gce_zone_network_health.yml
    assert "location" not in all_loaded_dt_dimensions
    assert "zone" not in all_loaded_dt_dimensions
    # gcp.instance.name used to be present under a number of fields - not checked here 
    
    # for kubernetes, old & new should always be present - consistency with other k8 integration dimensions
    assert "cluster_name" in all_loaded_dt_dimensions
    assert "container_name" in all_loaded_dt_dimensions
    assert "node_name" in all_loaded_dt_dimensions

def test_dimension_loading_config_compatibility_mode_true(monkeypatch: MonkeyPatchFixture):
    monkeypatch.setenv("COMPATIBILITY_MODE", "True")

    config = load_supported_services(context, [])

    assert len(config) == 87

    all_loaded_dt_dimensions = all_loaded_dt_dimension_labels(config)

    # new should be present
    assert "gcp.project.id" in all_loaded_dt_dimensions
    assert "gcp.region" in all_loaded_dt_dimensions
    assert "gcp.instance.name" in all_loaded_dt_dimensions

    # old should also be present - compatibilityMode on
    assert "project_id" in all_loaded_dt_dimensions
    assert "region" in all_loaded_dt_dimensions
    assert "location" in all_loaded_dt_dimensions
    # gcp.instance.name used to be present under a number of different fields - not checked here

    # for kubernetes, old & new for gcp.instance.name should always be present - consistency with other k8 integration dimensions
    assert "cluster_name" in all_loaded_dt_dimensions
    assert "container_name" in all_loaded_dt_dimensions
    assert "instance_name" in all_loaded_dt_dimensions

def all_loaded_dt_dimension_labels(config):
    all_dimensions_names = set()
    for service in config:
        all_dimensions_names.update([x.key_for_send_to_dynatrace for x in service.dimensions])
        for metric in service.metrics:
            all_dimensions_names.update([x.key_for_send_to_dynatrace for x in metric.dimensions])
    return all_dimensions_names

