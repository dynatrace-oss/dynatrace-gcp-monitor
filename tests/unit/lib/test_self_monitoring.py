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
from datetime import datetime

from lib.context import MetricsContext
from lib.self_monitoring import batch_time_series, create_self_monitoring_time_series
from lib.sfm.for_metrics.metrics_definitions import SfmKeys

expected_timeseries = {'timeSeries': [
    {'resource': {'type': 'generic_task',
                  'labels': {'project_id': None, 'location': 'us-east1', 'namespace': 'Local',
                             'job': 'Local', 'task_id': 'Local'}},
     'metric': {'type': 'custom.googleapis.com/dynatrace/connectivity',
                'labels': {'function_name': 'Local', 'dynatrace_tenant_url': None,
                           'reason': 'Ok'}}, 'valueType': 'INT64', 'metricKind': 'GAUGE',
     'points': [{'interval': {'endTime': '2022-12-19T14:38:53Z'}, 'value': {'int64Value': 1}}]},
    {'resource': {'type': 'generic_task',
                  'labels': {'project_id': None, 'location': 'us-east1', 'namespace': 'Local',
                             'job': 'Local', 'task_id': 'Local'}},
     'metric': {'type': 'custom.googleapis.com/dynatrace/ingest_lines',
                'labels': {'function_name': 'Local', 'dynatrace_tenant_url': None,
                           'status': 'Ok', 'project_id': 'project123'}}, 'valueType': 'INT64',
     'metricKind': 'GAUGE', 'points': [
        {'interval': {'endTime': '2022-12-19T14:38:53Z'}, 'value': {'int64Value': 100}}]},
    {'resource': {'type': 'generic_task',
                  'labels': {'project_id': None, 'location': 'us-east1',
                             'namespace': 'Local', 'job': 'Local', 'task_id': 'Local'}},
     'metric': {'type': 'custom.googleapis.com/dynatrace/ingest_lines',
                'labels': {'function_name': 'Local', 'dynatrace_tenant_url': None,
                           'status': 'Invalid', 'project_id': 'project123'}},
     'valueType': 'INT64', 'metricKind': 'GAUGE', 'points': [
        {'interval': {'endTime': '2022-12-19T14:38:53Z'}, 'value': {'int64Value': 200}}]},
    {'resource': {'type': 'generic_task',
                  'labels': {'project_id': None, 'location': 'us-east1',
                             'namespace': 'Local', 'job': 'Local', 'task_id': 'Local'}},
     'metric': {'type': 'custom.googleapis.com/dynatrace/ingest_lines',
                'labels': {'function_name': 'Local', 'dynatrace_tenant_url': None,
                           'status': 'Dropped', 'project_id': 'project123'}},
     'valueType': 'INT64', 'metricKind': 'GAUGE', 'points': [
        {'interval': {'endTime': '2022-12-19T14:38:53Z'}, 'value': {'int64Value': 300}}]},
    {'resource': {'type': 'generic_task',
                  'labels': {'project_id': None, 'location': 'us-east1',
                             'namespace': 'Local', 'job': 'Local', 'task_id': 'Local'}},
     'metric': {'type': 'custom.googleapis.com/dynatrace/phase_execution_time',
                'labels': {'function_name': 'Local', 'dynatrace_tenant_url': None,
                           'phase': 'setup', 'project_id': 'project123'}},
     'valueType': 'DOUBLE', 'metricKind': 'GAUGE', 'points': [
        {'interval': {'endTime': '2022-12-19T14:38:53Z'}, 'value': {'doubleValue': 321}}]},
    {'resource': {'type': 'generic_task',
                  'labels': {'project_id': None, 'location': 'us-east1',
                             'namespace': 'Local', 'job': 'Local', 'task_id': 'Local'}},
     'metric': {'type': 'custom.googleapis.com/dynatrace/phase_execution_time',
                'labels': {'function_name': 'Local', 'dynatrace_tenant_url': None,
                           'phase': 'fetch_gcp_data', 'project_id': 'project123'}},
     'valueType': 'DOUBLE', 'metricKind': 'GAUGE', 'points': [
        {'interval': {'endTime': '2022-12-19T14:38:53Z'}, 'value': {'doubleValue': 322}}]},
    {'resource': {'type': 'generic_task',
                  'labels': {'project_id': None, 'location': 'us-east1',
                             'namespace': 'Local', 'job': 'Local', 'task_id': 'Local'}},
     'metric': {'type': 'custom.googleapis.com/dynatrace/phase_execution_time',
                'labels': {'function_name': 'Local', 'dynatrace_tenant_url': None,
                           'phase': 'push_to_dynatrace', 'project_id': 'project123'}},
     'valueType': 'DOUBLE', 'metricKind': 'GAUGE', 'points': [
        {'interval': {'endTime': '2022-12-19T14:38:53Z'}, 'value': {'doubleValue': 323}}]},
    {'resource': {'type': 'generic_task',
                  'labels': {'project_id': None, 'location': 'us-east1',
                             'namespace': 'Local', 'job': 'Local', 'task_id': 'Local'}},
     'metric': {'type': 'custom.googleapis.com/dynatrace/request_count',
                'labels': {'response_code': '200', 'function_name': 'Local',
                           'dynatrace_tenant_url': None}}, 'valueType': 'INT64',
     'metricKind': 'GAUGE', 'points': [
        {'interval': {'endTime': '2022-12-19T14:38:53Z'}, 'value': {'int64Value': 3}}]},
]}


def test_create_self_monitoring_time_series():
    context = MetricsContext(
        gcp_session=None,
        dt_session=None,
        project_id_owner=None,
        token=None,
        execution_time=datetime.fromisoformat("2022-12-19T14:38:53"),
        execution_interval_seconds=30,
        dynatrace_api_key=None,
        dynatrace_url=None,
        print_metric_ingest_input=None,
        self_monitoring_enabled=None,
        scheduled_execution_id=None
    )

    context.sfm[SfmKeys.dynatrace_request_count].increment(200)
    context.sfm[SfmKeys.dynatrace_request_count].increment(200)
    context.sfm[SfmKeys.dynatrace_request_count].increment(200)

    context.sfm[SfmKeys.dynatrace_ingest_lines_ok_count].update("project123", 100)
    context.sfm[SfmKeys.dynatrace_ingest_lines_invalid_count].update("project123", 200)
    context.sfm[SfmKeys.dynatrace_ingest_lines_dropped_count].update("project123", 300)
    context.sfm[SfmKeys.setup_execution_time].update("project123", 321)
    context.sfm[SfmKeys.fetch_gcp_data_execution_time].update("project123", 322)
    context.sfm[SfmKeys.push_to_dynatrace_execution_time].update("project123", 323)

    timeseries = create_self_monitoring_time_series(context)

    assert timeseries == expected_timeseries


def test_batching():
    batched_series = batch_time_series({"timeSeries": [{"DATA": index} for index in range(1, 1001)]})
    assert len(batched_series) == 5
    for batch in batched_series:
        assert len(batch.get("timeSeries", [])) == 200


def test_batching_not_required():
    initial = {"timeSeries": [{"DATA": index} for index in range(1, 101)]}
    batched_series = batch_time_series(initial)
    assert len(batched_series) == 1
    assert initial == batched_series[0]
