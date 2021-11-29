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

from assertpy import assert_that

from lib.context import LoggingContext
from lib.utilities import load_activated_feature_sets, read_activation_yaml

context = LoggingContext("TEST")
MonkeyPatchFixture = NewType("MonkeyPatchFixture", Any)
ACTIVATION_CONFIG = "{services: [{service: pubsub_snapshot, featureSets: [default_metrics], vars: {filter_conditions: ''}},\
 {service: pubsub_subscription, featureSets: [default_metrics, test], vars: {filter_conditions: 'resource.labels.subscription_id=starts_with(\"test\")'}}]}"

ACTIVATION_CONFIG_WITHOUT_FEATURE_SET = "{services: [{service: services_to_be_activated, featureSets: [default_metrics], vars: {filter_conditions: ''}},\
 {service: you_shall_not_be_activated, vars: {filter_conditions: 'resource.labels.subscription_id=starts_with(\"test\")'}}]}"

ACTIVATION_CONFIG_WITH_EMPTY_FEATURE_SET = "{services: [{service: you_shall_not_be_activated, featureSets: [], vars: {filter_conditions: ''}},\
 {service: services_to_be_activated,featureSets: [default_metrics, test], vars: {filter_conditions: 'resource.labels.subscription_id=starts_with(\"test\")'}}]}"


def test_filtering_config_loaded(monkeypatch: MonkeyPatchFixture):
    monkeypatch.setenv("ACTIVATION_CONFIG", ACTIVATION_CONFIG)
    activation_yaml = read_activation_yaml()
    activated_service_names = load_activated_feature_sets(context, activation_yaml)
    assert_that(activated_service_names).contains_only("pubsub_subscription/default_metrics", "pubsub_subscription/test",
                                                       "pubsub_snapshot/default_metrics")


def test_filtering_missing_configs(monkeypatch: MonkeyPatchFixture):
    monkeypatch.setenv("ACTIVATION_CONFIG", "{services: []}")
    activation_yaml = read_activation_yaml()
    config = load_activated_feature_sets(context, activation_yaml)
    assert len(config) == 0


def test_filtering_services_without_feature_sets(monkeypatch: MonkeyPatchFixture):
    monkeypatch.setenv("ACTIVATION_CONFIG", ACTIVATION_CONFIG_WITHOUT_FEATURE_SET)
    activation_yaml = read_activation_yaml()
    activated_service_names = load_activated_feature_sets(context, activation_yaml)
    assert_that(activated_service_names).contains_only("services_to_be_activated/default_metrics")


def test_services_with_an_empty_feature_sets(monkeypatch: MonkeyPatchFixture):
    monkeypatch.setenv("ACTIVATION_CONFIG", ACTIVATION_CONFIG_WITH_EMPTY_FEATURE_SET)
    activation_yaml = read_activation_yaml()
    activated_service_names = load_activated_feature_sets(context, activation_yaml)
    assert_that(activated_service_names).contains_only("services_to_be_activated/default_metrics", "services_to_be_activated/test")
