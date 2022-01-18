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
from lib.context import LoggingContext
from lib.logs.metadata_engine import SourceMatcher, _create_config_rule

context = LoggingContext("TEST")


def test_resource_type_eq_source_matcher():
    matcher = SourceMatcher(context, "resourceType", "$eq('TEST')")
    assert matcher.match({}, {"gcp.resource.type": "TEST"})
    assert not matcher.match({}, {"gcp.resource.type": "NOT_TEST"})
    assert not matcher.match({}, {})


def test_resource_type_contains_source_matcher():
    matcher = SourceMatcher(context, "resourceType", "$contains('TEST')")
    assert matcher.match({}, {"gcp.resource.type": "GCP_TEST"})
    assert not matcher.match({}, {"gcp.resource.type": "BEST"})
    assert not matcher.match({}, {})


def test_resource_type_prefix_source_matcher():
    matcher = SourceMatcher(context, "resourceType", "$prefix('TEST')")
    assert matcher.match({}, {"gcp.resource.type": "TEST_GCP"})
    assert not matcher.match({}, {"gcp.resource.type": "GCP_TEST"})
    assert not matcher.match({}, {})


def test_create_valid_config_rule():
    rule_json = {
        "sources": [{"sourceType": "logs", "source": "resourceType", "condition": "$eq('MICROSOFT.APIMANAGEMENT/SERVICE')"}]
    }
    assert _create_config_rule(context, "TEST", rule_json)


def test_create_invalid_config_rule_source_missing_field():
    rule_json = {
        "sources": [{"sourceType": "logs", "condition": "$eq('MICROSOFT.APIMANAGEMENT/SERVICE')"}]
    }
    assert not _create_config_rule(context, "TEST", rule_json)


def test_create_invalid_config_rule_invalid_source():
    rule_json = {
        "sources": [{"sourceType": "logs", "source": "INVALID", "condition": "$eq('MICROSOFT.APIMANAGEMENT/SERVICE')"}]
    }
    assert not _create_config_rule(context, "TEST", rule_json)


def test_default_rule_can_have_no_sources():
    rule_json = {
        "sources": []
    }
    assert _create_config_rule(context, "default", rule_json)