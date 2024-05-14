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

import json
import os
import re
from dataclasses import dataclass
from os import listdir
from os.path import isfile
from typing import Dict, List, Optional, Any

import jmespath

from lib.context import LoggingContext
from lib.logs.jmespath import JMESPATH_OPTIONS

_CONDITION_COMPARATOR_MAP = {
    "$eq".casefold(): lambda x, y: str(x).casefold() == str(y).casefold(),
    "$prefix".casefold(): lambda x, y: str(x).casefold().startswith(str(y).casefold()),
    "$contains".casefold(): lambda x, y: str(y).casefold() in str(x).casefold(),
}

_SOURCE_VALUE_EXTRACTOR_MAP = {
    "resourceType".casefold(): lambda record, parsed_record: parsed_record.get("gcp.resource.type", None),
    "logName".casefold(): lambda record, parsed_record: record.get("logName", None),
}

ATTRIBUTE_AUDIT_IDENTITY = "audit.identity"

ATTRIBUTE_AUDIT_ACTION = "audit.action"

ATTRIBUTE_AUDIT_RESULT = "audit.result"

ATTRIBUTE_SEVERITY = "severity"

ATTRIBUTE_DT_LOGPATH = "log.source"

ATTRIBUTE_TIMESTAMP = "timestamp"

ATTRIBUTE_CONTENT = "content"

ATTRIBUTE_CLOUD_REGION = "cloud.region"

ATTRIBUTE_CLOUD_PROVIDER = "cloud.provider"

ATTRIBUTE_GCP_REGION = "gcp.region"

ATTRIBUTE_GCP_PROJECT_ID = "gcp.project.id"

ATTRIBUTE_GCP_INSTANCE_ID = "gcp.instance.id"

ATTRIBUTE_GCP_CLOUD_FUNCTION_NAME = 'gcp.instance.cloud_function_name'

ATTRIBUTE_GCP_INSTANCE_NAME = "gcp.instance.name"

ATTRIBUTE_GCP_RESOURCE_TYPE = "gcp.resource.type"

ATTRIBUTE_CLOUD_FUNCTION_ID = "faas.id"

ATTRIBUTE_CLOUD_FUNCTION_NAME = "faas.name"

DEFAULT_RULE_NAME = "default"

COMMON_RULE_NAME = "common"

AUDIT_LOGS_RULE = "audit_logs"

SPECIAL_RULE_NAMES = (DEFAULT_RULE_NAME, COMMON_RULE_NAME)


@dataclass(frozen=True)
class Attribute:
    key: str
    pattern: str


class SourceMatcher:
    source: str
    condition: str
    valid = True

    _evaluator = None
    _operand = None
    _source_value_extractor = None

    def __init__(self, context: LoggingContext, source: str, condition: str):
        self.source = source
        self.condition = condition
        for key in _CONDITION_COMPARATOR_MAP:
            if condition.startswith(key):
                self._evaluator = _CONDITION_COMPARATOR_MAP[key]
                break
        operands = re.findall(r"'(.*?)'", condition, re.DOTALL)
        self._operand = operands[0] if operands else None
        self._source_value_extractor = _SOURCE_VALUE_EXTRACTOR_MAP.get(source.casefold(), None)

        if not self._source_value_extractor:
            context.log(f"Unsupported source type: '{source}'")
            self.valid = False
        if not self._evaluator or not self._operand:
            context.log(f"Failed to parse condition macro for expression: '{condition}'")
            self.valid = False

    def match(self, record: Dict, parsed_record: Dict) -> bool:
        value = self._extract_value(record, parsed_record)
        return self._evaluator(value, self._operand)

    def _extract_value(self, record: Dict, parsed_record: Dict) -> Any:
        return self._source_value_extractor(record, parsed_record)


def apply_common_rules(record, parsed_record):
    def get_severity():
        parsed_record["severity"] = record.get("severity", "INFO")

    def get_cloud_provider():
        parsed_record["cloud.provider"] = "gcp"

    def get_cloud_region(resource):
        gcp_region = (
            resource.get("labels", {}).get("region")
            or resource.get("labels", {}).get("location")
            or resource.get("labels", {}).get("zone")
        )

        if gcp_region:
            parsed_record["gcp.region"] = gcp_region
            parsed_record["cloud.region"] = gcp_region

    def get_gcp_project_id(resource):

        project_id = resource.get("labels", {}).get("project_id", None)
        if project_id:
            parsed_record["gcp.project.id"] = project_id

    def get_gcp_instance_id(resource):

        instance_id = resource.get("labels", {}).get("instance_id", None)
        if instance_id and len(instance_id) >= 3:
            parsed_record["gcp.instance.id"] = instance_id

    def get_resource_type(resource):
        resource_type = resource.get("type", None)
        if resource_type:
            parsed_record["gcp.resource.type"] = resource_type

    def get_timestamp():
        if "timestamp" in record:
            parsed_record["timestamp"] = record["timestamp"]

    def get_log_source():
        if "logName" in record:
            parsed_record["log.source"] = record["logName"]

    get_severity()
    get_cloud_provider()
    get_timestamp()
    get_log_source()

    resource = record.get("resource", None)
    if resource:
        get_resource_type(resource)
        get_cloud_region(resource)
        get_gcp_project_id(resource)
        get_gcp_instance_id(resource)


@dataclass(frozen=True)
class ConfigRule:
    entity_type_name: str
    source_matchers: List[SourceMatcher]
    attributes: List[Attribute]


class MetadataEngine:
    rules: List[ConfigRule]
    audit_logs_rules: List[ConfigRule]
    default_rule: ConfigRule = None
    common_rule: ConfigRule = None
    context: LoggingContext

    def __init__(self):
        self.rules = []
        self.audit_logs_rules = []
        self._load_configs()

    def _load_configs(self):
        context = LoggingContext("ME startup")
        working_directory = os.path.dirname(os.path.realpath(__file__))
        config_directory = os.path.join(working_directory, "../../config_logs")
        config_files = []

        for root, _, files in os.walk(config_directory):
            for file in files:
                if _is_json_file(file):
                    config_files.append(os.path.join(root, file))

        for file in config_files:
            config_file_path = os.path.join(config_directory, file)
            try:
                with open(config_file_path) as config_file:
                    config_json = json.load(config_file)
                    if config_json.get("name", "") == DEFAULT_RULE_NAME:
                        self.default_rule = _create_config_rules(context, config_json)[0]
                    elif config_json.get("name", "") == COMMON_RULE_NAME:
                        self.common_rule = _create_config_rules(context, config_json)[0]
                    elif config_json.get("name", "").startswith(AUDIT_LOGS_RULE):
                        self.audit_logs_rules = _create_config_rules(context, config_json)
                    else:
                        self.rules.extend(_create_config_rules(context, config_json))
            except Exception as e:
                context.exception(f"Failed to load configuration file: '{config_file_path}'")

    @staticmethod
    def _apply_rules(context, rules: List[ConfigRule], record: Dict, parsed_record: Dict) -> bool:
        any_rule_applied = False
        for rule in rules:
            if _check_if_rule_applies(rule, record, parsed_record):
                _apply_rule(context, rule, record, parsed_record)
                any_rule_applied = True
        return any_rule_applied

    def apply(self, context: LoggingContext, record: Dict, parsed_record: Dict):
        try:
            # Old rules from _config_logs/_common/common.json
            #if self.common_rule:
            #    _apply_rule(context, self.common_rule, record, parsed_record)
            #Apply common rules
            apply_common_rules(record, parsed_record)

            any_rule_applied = self._apply_rules(context, self.rules, record, parsed_record)
            any_audit_rule_applied = self._apply_rules(context, self.audit_logs_rules, record, parsed_record)
            # No matching rule has been found, applying the default rule
            no_rule_applied = not (any_rule_applied or any_audit_rule_applied)
            if no_rule_applied and self.default_rule:
                _apply_rule(context, self.default_rule, record, parsed_record)
        except Exception as e:
            context.t_exception(f"Encountered exception when running Rule Engine. {e}")


def _check_if_rule_applies(rule: ConfigRule, record: Dict, parsed_record: Dict):
    for matcher in rule.source_matchers:
        if not matcher.match(record, parsed_record):
            return False
    return True


def _apply_rule(context: LoggingContext, rule: ConfigRule, record: Dict, parsed_record: Dict):
    for attribute in rule.attributes:
        try:
            value = jmespath.search(attribute.pattern, record, JMESPATH_OPTIONS)
            if value:
                parsed_record[attribute.key] = value
        except Exception:
            context.t_exception(f"Encountered exception when evaluating attribute {attribute} of rule for {rule.entity_type_name}",
                              f"rule-attribute-evaluation-{rule.entity_type_name}exception")


def _create_sources(context: LoggingContext, sources_json: List[Dict]) -> List[SourceMatcher]:
    result = []

    for source_json in sources_json:
        source = source_json.get("source", None)
        condition = source_json.get("condition", None)
        source_matcher = None

        if source and condition:
            source_matcher = SourceMatcher(context, source, condition)

        if source_matcher and source_matcher.valid:
            result.append(source_matcher)
        else:
            context.log(f"Encountered invalid rule source, parameters were: source= {source}, condition = {condition}")
            return []

    return result


def _create_attributes(context: LoggingContext, attributes_json: List[Dict]) -> List[Attribute]:
    result = []

    for source_json in attributes_json:
        key = source_json.get("key", None)
        pattern = source_json.get("pattern", None)

        if key and pattern:
            result.append(Attribute(key, pattern))
        else:
            context.log(f"Encountered invalid rule attribute with missing parameter, parameters were: key = {key}, pattern = {pattern}")

    return result


def _create_config_rule(context: LoggingContext, entity_name: str, rule_json: Dict) -> Optional[ConfigRule]:
    sources_json = rule_json.get("sources", [])
    if entity_name not in SPECIAL_RULE_NAMES and not sources_json:
        context.log(f"Encountered invalid rule with missing sources for config entry named {entity_name}")
        return None
    sources = _create_sources(context, sources_json)
    if entity_name not in SPECIAL_RULE_NAMES and not sources:
        context.log(f"Encountered invalid rule with invalid sources for config entry named {entity_name}: {sources_json}")
        return None
    attributes = _create_attributes(context, rule_json.get("attributes", []))
    return ConfigRule(entity_type_name=entity_name, source_matchers=sources, attributes=attributes)


def _create_config_rules(context: LoggingContext, config_json: Dict) -> List[ConfigRule]:
    name = config_json.get("name", "")
    created_rules = [_create_config_rule(context, name, rule_json) for rule_json in config_json.get("rules", [])]
    return [created_rule for created_rule in created_rules if created_rule is not None]


def _is_json_file(file: str) -> bool:
    return file.endswith(".json")