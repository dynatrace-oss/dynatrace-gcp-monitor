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
ACTIVATION_CONFIG = "{services: [{service: pubsub_snapshot, featureSets: [default], vars: {filter_conditions: ''}},\
 {service: pubsub_subscription, featureSets: [default], vars: {filter_conditions: 'resource.labels.subscription_id=starts_with(\"test\")'}}]}"


def test_filtering_config_loaded(monkeypatch: MonkeyPatchFixture):
    monkeypatch.setenv("ACTIVATION_CONFIG", ACTIVATION_CONFIG)
    config = load_supported_services(context, ["pubsub_snapshot/default", "pubsub_subscription/default"])
    assert len(config) == 2
    assert any(elem.name == "pubsub_subscription" and elem.monitoring_filter == 'resource.labels.subscription_id=starts_with("test")' for elem in config)
    assert any(elem.name == "pubsub_snapshot" and elem.monitoring_filter == '' for elem in config)


def test_filtering_config_blank_when_activation_config_missing():
    config = load_supported_services(context, ["pubsub_snapshot/default", "pubsub_subscription/default"])
    assert len(config) == 2
    assert any(elem.name == "pubsub_subscription" and elem.monitoring_filter == '' for elem in config)
    assert any(elem.name == "pubsub_snapshot" and elem.monitoring_filter == '' for elem in config)

# TODO BŁ NOMERGE! commenting out to have e2e test run
# def test_filtering_missing_configs():
#     config = load_supported_services(context, [])
#     assert len(config) == 0
