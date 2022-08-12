# Dynatrace Google Cloud Integration Hacking instructions

## Development environment setup

To run worker function locally you have to have Python dev environment installed: `Python 3.8` with `pip` tool.

to install all the dependencies run 
```shell script
pip install -r requirements-dev.txt
pip install -r src\requirements.txt
pip install -r tests\requirements.txt
pip install --only-binary :all: cryptography==3.4.7 #cryptography library in Windows env requires this special handling or rustup installed
```

##Running single local run
Run `local_test.py` with env_vars set according to the table below. 

To run metrics ingest worker function run `local_test.py` script file. 
This runs a single run, and then returns. Some expection may appear in Win env, and self-monitoring metrics query can fail. 

To run logs ingest worker function run `local_test.py` script file with `OPERATION_MODE` set to `Logs` 

##Running periodic local run
Run `run_docker.py` with env_vars set according to the table below.

As opposed to `local_test.py`, this runs continuously.

## Environment variables

Worker function execution can be tweaked with environment variables. In Google Function you can input them when deploying/editing the function:

### Metric processing configuration variables

| Variable name | description   | default value |
| ----------------- | ------------- | ----------- |
| GCP_PROJECT | GCP project id | |
| PRINT_METRIC_INGEST_INPUT | boolean value, if true will print full MINT ingest input. Allowed values: `true`/`yes`, `false`/`no` | `false` |
| DYNATRACE_ACCESS_KEY_SECRET_NAME | name of environment variable or Google Secret Manager Secret containing Dynatrace Access Key | DYNATRACE_ACCESS_KEY |
| DYNATRACE_URL_SECRET_NAME | name of environment variable or Google Secret Manager Secret containing Dynatrace URL | DYNATRACE_URL |
| GOOGLE_APPLICATION_CREDENTIALS | path to GCP service account key file | |
| MAXIMUM_METRIC_DATA_POINTS_PER_MINUTE | Max number of MINT ingest lines processed in one minute interval | 1 000 000 |
| METRIC_INGEST_BATCH_SIZE | size of MINT ingest batch sent to Dynatrace cluster | 1000 |
| REQUIRE_VALID_CERTIFICATE | determines whether worker will verify SSL certificate of Dynatrace endpoint. Allowed values: `true`/`yes`, `false`/`no` | `true` |
| SERVICE_USAGE_BOOKING | `source` if API calls should use default billing mechanism, `destination` if they should be billed per project | `source` |
| USE_PROXY | Depending on value of this flag, function will use proxy settings for either Dynatrace, GCP API or both. Allowed values: `ALL`, `DT_ONLY`, `GCP_ONLY` |  |
| HTTP_PROXY | Set the proxy address. To be used in conjunction with USE_PROXY |  |
| HTTPS_PROXY | Set the proxy address. To be used in conjunction with USE_PROXY |  |
| MAX_DIMENSION_NAME_LENGTH | The maximum length of the dimension name sent to the MINT API. Longer names are truncated to the value indicated. Allowed values: positive integers. | 100 |
| MAX_DIMENSION_VALUE_LENGTH | The maximum length of the dimension value sent to the MINT API. Longer values are truncated to the value indicated. Allowed values: positive integers. | 250 |
| SELF_MONITORING_ENABLED | Send custom metrics to GCP to diagnose quickly if your dynatrace-gcp-function processes and sends metrics to Dynatrace properly. Allowed values: `true`/`yes`, `false`/`no` | `false` |
| QUERY_INTERVAL_MIN | Metrics polling interval in minutes. Allowed values: 1 - 6 | 3 |
| ACTIVATION_CONFIG | Dimension filtering config (see `gcpServicesYaml` property in [values.yaml](https://github.com/dynatrace-oss/dynatrace-gcp-function/blob/master/k8s/helm-chart/dynatrace-gcp-function/values.yaml) file) minified to single line json |  |

### Log processing configuration variables

| Variable name | description   | default value |
| ----------------- | ------------- | ----------- |
| DYNATRACE_ACCESS_KEY_SECRET_NAME | name of environment variable or Google Secret Manager Secret containing Dynatrace Access Key | DYNATRACE_ACCESS_KEY |
| DYNATRACE_LOG_INGEST_URL_SECRET_NAME | name of environment variable or Google Secret Manager Secret containing Dynatrace URL | DYNATRACE_LOG_INGEST_URL |
| GOOGLE_APPLICATION_CREDENTIALS | path to GCP service account key file | |
| REQUIRE_VALID_CERTIFICATE | determines whether worker will verify SSL certificate of Dynatrace endpoint. Allowed values: `true`/`yes`, `false`/`no` | `true` |
| DYNATRACE_LOG_INGEST_CONTENT_MAX_LENGTH | determines max content length of log event. Should be the same or lower than on cluster | 8192 characters |
| DYNATRACE_LOG_INGEST_ATTRIBUTE_VALUE_MAX_LENGTH | Max length of log event attribute value. If it surpasses server limit, Content will be truncated | 250 |
| DYNATRACE_LOG_INGEST_REQUEST_MAX_EVENTS | Max number of log events in single payload to logs ingest endpoint. If it surpasses server limit, payload will be rejected with 413 code  | 5000 |
| DYNATRACE_LOG_INGEST_REQUEST_MAX_SIZE | Max size in bytes of single payload to logs ingest endpoint. If it surpasses server limit, payload will be rejected with 413 code | 1048576 (1 mb) |
| DYNATRACE_LOG_INGEST_EVENT_MAX_AGE_SECONDS | Determines max age of forwarded log event. Should be the same or lower than on cluster | 1 day |
| GCP_PROJECT | GCP project of log sink pubsub subscription | |
| USE_PROXY | Depending on value of this flag, function will use proxy settings for either Dynatrace, GCP API or both.
| HTTP_PROXY | Set the proxy address. To be used in conjunction with USE_PROXY |  |
| HTTPS_PROXY | Set the proxy address. To be used in conjunction with USE_PROXY |  |
| LOGS_SUBSCRIPTION_ID | subscription id of log sink pubsub subscription | |
| DYNATRACE_LOG_INGEST_SENDING_WORKER_EXECUTION_PERIOD | Period of sending batched logs to Dynatrace | 60 seconds |
| DYNATRACE_TIMEOUT_SECONDS | Timeout of request to Dynatrace Log Ingest | 30 seconds |
| SELF_MONITORING_ENABLED | Send custom metrics to GCP to diagnose quickly if your gcp-log-forwarder processes and sends logs to Dynatrace properly. Allowed values: `true`/`yes`, `false`/`no` | `false` |


## Building custom extension for Google Cloud service
### Introduction
Building custom extension for GCP service allows to customize metrics / dimensions that are ingested to Dynatrace AND/OR to ingest metrics for service not officially supported by Dynatrace extensions. 

Limitations:
* custom extensions for `dynatrace-gcp-function` are not supported by Dynatrace
* custom extension will work **only** on Kubernetes deployment

`dynatrace-gcp-function` uses Dynatrace Extension Framework 2.0 to package support for GCP Services (metrics, topology rules, dasboards etc). Latest version of official GCP extensions is listed in [extensions-list.txt](https://d1twjciptxxqvo.cloudfront.net/extensions-list.txt) manifest file.

Reference:
* [Extension YAML file](https://www.dynatrace.com/support/help/extend-dynatrace/extensions20/extension-yaml)
* [Sign extensions](https://www.dynatrace.com/support/help/extend-dynatrace/extensions20/sign-extension)

As **an example**, I'll examplain how to customize `Google Compute Engine` extension. 

Required tools:
* IDE for yaml, (for example: `vscode` with `YAML` extension installed)
* openssl
* zip

### Building custom extension

#### 1. Get the name of latest `google-compute-engine` extension
```
GCE_EXTENSION_VERSION=$(curl -s https://d1twjciptxxqvo.cloudfront.net/extensions-list.txt | grep google-compute-engine)
```
 
#### 2. Download the extension
```
wget https://d1twjciptxxqvo.cloudfront.net/${GCE_EXTENSION_VERSION}
```

#### 3. Unzip extension
```
unzip google-compute-engine-0.0.9.zip
```

#### 4. Unzip extension defintion
```
mkdir extension && unzip extension.zip -d ./extension
```

#### 5. Customize extension defintion

```
code ./extension/extension.yaml
```

* change the value of `name:` attribute from `com.dynatrace.extension.google-compute-engine` to `custom:com.dynatrace.extension.gce` (custom extension must begin with `custom:` prefix, extension name cannot be longer than 50 chars, that's why the service name is shortened)
* change the `version:` attribute to `version: 0.0.1`
* change `author.name:` to the Developer name, for example `Pawel Siwek`
* add custom dashboard for GCE, add attribute `dashboards.path` and point to the dashboard definition I've created dashboards `dashboards/gce.json`
* within the `gcp.service` and `metrics` list leave only desired metrics & dimension, in my example:
    1) `cloud.gcp.compute_googleapis_com.instance.network.received_bytes_count`
    2) `cloud.gcp.compute_googleapis_com.instance.network.sent_bytes_count`
    3) `cloud.gcp.compute_googleapis_com.instance.cpu.utilization`

the extension after customization will look following way:
```
name: custom:com.dynatrace.extension.gce
version: 0.0.2
minDynatraceVersion: '1.229'
author:
  name: Pawel Siwek
vars:
- id: filter_conditions
  displayName: Metric query filter for which metrics should be queried
  type: variables
metrics:
- key: cloud.gcp.compute_googleapis_com.instance.cpu.utilization
  metadata:
    displayName: CPU utilization
    unit: Percent
- key: cloud.gcp.compute_googleapis_com.instance.network.received_bytes_count
  metadata:
    displayName: Received bytes
    unit: Byte
- key: cloud.gcp.compute_googleapis_com.instance.network.sent_bytes_count
  metadata:
    displayName: Sent bytes
    unit: Byte
alerts:
- path: alerts/cpu_utilization.json
dashboards:

topology:
  types:
  - name: cloud:gcp:gce_instance
    displayName: Google VM Instance
    rules:
    - idPattern: //compute.googleapis.com/projects/{gcp.project.id}/zones/{gcp.region}/instance/{gcp.instance.id}
      instanceNamePattern: '{gcp.instance.id}'
      iconPattern: google-cloud-signet
      sources:
      - sourceType: Metrics
        condition: $prefix(cloud.gcp.compute_googleapis_com.mirroring)
      - sourceType: Metrics
        condition: $prefix(cloud.gcp.agent_googleapis_com)
      - sourceType: Metrics
        condition: $prefix(cloud.gcp.compute_googleapis_com.guest)
      - sourceType: Metrics
        condition: $prefix(cloud.gcp.networking_googleapis_com.vm_flow)
      - sourceType: Metrics
        condition: $prefix(cloud.gcp.compute_googleapis_com.instance)
      - sourceType: Metrics
        condition: $prefix(cloud.gcp.firewallinsights_googleapis_com.vm)
      - sourceType: Metrics
        condition: $prefix(cloud.gcp.istio_io.service)
      requiredDimensions: []
      attributes:
      - key: project_id
        displayName: project_id
        pattern: '{gcp.project.id}'
      - key: zone
        displayName: zone
        pattern: '{gcp.region}'
      - key: instance_id
        displayName: instance_id
        pattern: '{gcp.instance.id}'
  - name: cloud:gcp:instance_group
    displayName: Google Instance Group
    rules:
    - idPattern: //compute.googleapis.com/projects/{gcp.project.id}/locations/{gcp.region}/instanceGroups/{gcp.instance.id}
      instanceNamePattern: '{gcp.instance.name}'
      iconPattern: google-cloud-signet
      sources:
      - sourceType: Metrics
        condition: $prefix(cloud.gcp.compute_googleapis_com.instance_group)
      requiredDimensions: []
      attributes:
      - key: location
        displayName: location
        pattern: '{gcp.region}'
      - key: instance_group_id
        displayName: instance_group_id
        pattern: '{gcp.instance.id}'
      - key: project_id
        displayName: project_id
        pattern: '{gcp.project.id}'
      - key: instance_group_name
        displayName: instance_group_name
        pattern: '{gcp.instance.name}'
  - name: cloud:gcp:autoscaler
    displayName: Google Autoscaler
    rules:
    - idPattern: //autoscaler.googleapis.com/projects/{gcp.project.id}/locations/{gcp.region}/autoscalers/{gcp.instance.id}
      instanceNamePattern: '{gcp.instance.id}'
      iconPattern: google-cloud-signet
      sources:
      - sourceType: Metrics
        condition: $prefix(cloud.gcp.autoscaler_googleapis_com)
      requiredDimensions: []
      attributes:
      - key: location
        displayName: location
        pattern: '{gcp.region}'
      - key: autoscaler_id
        displayName: autoscaler_id
        pattern: '{gcp.instance.id}'
      - key: autoscaler_name
        displayName: autoscaler_name
        pattern: '{gcp.instance.name}'
      - key: project_id
        displayName: project_id
        pattern: '{gcp.project.id}'
  - name: cloud:gcp:tpu_worker
    displayName: Google Cloud TPU Worker
    rules:
    - idPattern: //tpu.googleapis.com/projects/{gcp.project.id}/locations/{gcp.region}/nodes/{node_id}
      instanceNamePattern: '{node_id}'
      iconPattern: google-cloud-signet
      sources:
      - sourceType: Metrics
        condition: $prefix(tpu.googleapis.com)
      requiredDimensions: []
      attributes:
      - key: zone
        displayName: zone
        pattern: '{gcp.region}'
      - key: worker_id
        displayName: worker_id
        pattern: '{gcp.instance.id}'
      - key: project_id
        displayName: project_id
        pattern: '{gcp.project.id}'
      - key: node_id
        displayName: node_id
        pattern: '{node_id}'
gcp:
- service: gce_instance
  gcpMonitoringFilter: var:filter_conditions
  dimensions:
  - value: label:resource.labels.project_id
    key: gcp.project.id
  - value: label:resource.labels.instance_id
    key: gcp.instance.id
  - value: label:resource.labels.zone
    key: gcp.region
  - value: label:resource.labels.project_id
    key: project_id
  - value: label:resource.labels.instance_id
    key: instance_id
  - value: label:resource.labels.zone
    key: zone
  metrics:
  - value: metric:compute.googleapis.com/instance/cpu/utilization
    key: cloud.gcp.compute_googleapis_com.instance.cpu.utilization
    type: gauge
    gcpOptions:
      ingestDelay: 240
      samplePeriod: 60
      valueType: DOUBLE
      metricKind: GAUGE
      unit: 10^2.%
    dimensions:
    - value: label:metric.labels.instance_name
      key: instance_name
    - value: label:metric.labels.instance_name
      key: gcp.instance.name
  - value: metric:compute.googleapis.com/instance/network/received_bytes_count
    key: cloud.gcp.compute_googleapis_com.instance.network.received_bytes_count
    type: count,delta
    gcpOptions:
      ingestDelay: 240
      samplePeriod: 60
      valueType: INT64
      metricKind: DELTA
      unit: By
    dimensions:
    - value: label:metric.labels.instance_name
      key: instance_name
    - value: label:metric.labels.instance_name
      key: gcp.instance.name
    - value: label:metric.labels.loadbalanced
      key: loadbalanced
  - value: metric:compute.googleapis.com/instance/network/sent_bytes_count
    key: cloud.gcp.compute_googleapis_com.instance.network.sent_bytes_count
    type: count,delta
    gcpOptions:
      ingestDelay: 240
      samplePeriod: 60
      valueType: INT64
      metricKind: DELTA
      unit: By
    dimensions:
    - value: label:metric.labels.instance_name
      key: instance_name
    - value: label:metric.labels.instance_name
      key: gcp.instance.name
    - value: label:metric.labels.loadbalanced
      key: loadbalanced
  featureSet: default_metrics

```

####  6. Add dashboard 

create directory `dashboards`
```
mkdir dashboards
```

edit dashboard defintion
```
code ./extension/dashboards/gce.json
```

Sample dashboard for GCE:
```
{
  "metadata": {
    "configurationVersions": [
      6
    ],
    "clusterVersion": "1.249.4.20220812-050055"
  },
  "dashboardMetadata": {
    "name": "Google Compute Engine",
    "shared": false,
    "owner": "pawel.siwek@dynatrace.com",
    "popularity": 10,
    "hasConsistentColors": false
  },
  "tiles": [
    {
      "name": "Received bytes",
      "tileType": "DATA_EXPLORER",
      "configured": true,
      "bounds": {
        "top": 608,
        "left": 684,
        "width": 684,
        "height": 266
      },
      "tileFilter": {},
      "customName": "Data explorer results",
      "queries": [
        {
          "id": "B",
          "metric": "cloud.gcp.compute_googleapis_com.instance.network.received_bytes_count",
          "timeAggregation": "DEFAULT",
          "splitBy": [
            "gcp.instance.name"
          ],
          "sortBy": "DESC",
          "filterBy": {
            "nestedFilters": [],
            "criteria": []
          },
          "limit": 100,
          "enabled": true
        }
      ],
      "visualConfig": {
        "type": "GRAPH_CHART",
        "global": {
          "hideLegend": false
        },
        "rules": [
          {
            "matcher": "B:",
            "properties": {
              "color": "DEFAULT"
            },
            "seriesOverrides": []
          }
        ],
        "axes": {
          "xAxis": {
            "displayName": "",
            "visible": true
          },
          "yAxes": [
            {
              "displayName": "",
              "visible": true,
              "min": "AUTO",
              "max": "AUTO",
              "position": "LEFT",
              "queryIds": [
                "B"
              ],
              "defaultAxis": true
            }
          ]
        },
        "heatmapSettings": {
          "yAxis": "VALUE"
        },
        "thresholds": [
          {
            "axisTarget": "LEFT",
            "rules": [
              {
                "color": "#7dc540"
              },
              {
                "color": "#f5d30f"
              },
              {
                "color": "#dc172a"
              }
            ],
            "queryId": "",
            "visible": true
          }
        ],
        "tableSettings": {
          "isThresholdBackgroundAppliedToCell": false
        },
        "graphChartSettings": {
          "connectNulls": false
        },
        "honeycombSettings": {
          "showHive": true,
          "showLegend": true,
          "showLabels": false
        }
      },
      "queriesSettings": {
        "resolution": ""
      },
      "metricExpressions": [
        "resolution=null&(cloud.gcp.compute_googleapis_com.instance.network.received_bytes_count:splitBy(\"gcp.instance.name\"):sort(value(auto,descending)):limit(100)):limit(100):names"
      ]
    },
    {
      "name": "Send bytes",
      "tileType": "DATA_EXPLORER",
      "configured": true,
      "bounds": {
        "top": 608,
        "left": 0,
        "width": 684,
        "height": 266
      },
      "tileFilter": {},
      "customName": "Data explorer results",
      "queries": [
        {
          "id": "A",
          "metric": "cloud.gcp.compute_googleapis_com.instance.network.sent_bytes_count",
          "timeAggregation": "DEFAULT",
          "splitBy": [
            "gcp.instance.name"
          ],
          "sortBy": "DESC",
          "filterBy": {
            "nestedFilters": [],
            "criteria": []
          },
          "limit": 100,
          "enabled": true
        }
      ],
      "visualConfig": {
        "type": "GRAPH_CHART",
        "global": {
          "hideLegend": false
        },
        "rules": [
          {
            "matcher": "A:",
            "properties": {
              "color": "DEFAULT"
            },
            "seriesOverrides": []
          }
        ],
        "axes": {
          "xAxis": {
            "displayName": "",
            "visible": true
          },
          "yAxes": [
            {
              "displayName": "",
              "visible": true,
              "min": "AUTO",
              "max": "AUTO",
              "position": "LEFT",
              "queryIds": [
                "A"
              ],
              "defaultAxis": true
            }
          ]
        },
        "heatmapSettings": {
          "yAxis": "VALUE"
        },
        "thresholds": [
          {
            "axisTarget": "LEFT",
            "rules": [
              {
                "color": "#7dc540"
              },
              {
                "color": "#f5d30f"
              },
              {
                "color": "#dc172a"
              }
            ],
            "queryId": "",
            "visible": true
          }
        ],
        "tableSettings": {
          "isThresholdBackgroundAppliedToCell": false
        },
        "graphChartSettings": {
          "connectNulls": false
        },
        "honeycombSettings": {
          "showHive": true,
          "showLegend": true,
          "showLabels": false
        }
      },
      "queriesSettings": {
        "resolution": ""
      },
      "metricExpressions": [
        "resolution=null&(cloud.gcp.compute_googleapis_com.instance.network.sent_bytes_count:splitBy(\"gcp.instance.name\"):sort(value(auto,descending)):limit(100)):limit(100):names"
      ]
    },
    {
      "name": "CPU utilization",
      "tileType": "DATA_EXPLORER",
      "configured": true,
      "bounds": {
        "top": 304,
        "left": 684,
        "width": 684,
        "height": 304
      },
      "tileFilter": {},
      "customName": "Data explorer results",
      "queries": [
        {
          "id": "A",
          "metric": "cloud.gcp.compute_googleapis_com.instance.cpu.utilization",
          "timeAggregation": "DEFAULT",
          "splitBy": [
            "gcp.instance.name"
          ],
          "sortBy": "DESC",
          "filterBy": {
            "nestedFilters": [],
            "criteria": []
          },
          "limit": 100,
          "enabled": true
        }
      ],
      "visualConfig": {
        "type": "GRAPH_CHART",
        "global": {
          "hideLegend": false
        },
        "rules": [
          {
            "matcher": "A:",
            "properties": {
              "color": "DEFAULT"
            },
            "seriesOverrides": []
          }
        ],
        "axes": {
          "xAxis": {
            "displayName": "",
            "visible": true
          },
          "yAxes": [
            {
              "displayName": "",
              "visible": true,
              "min": "0",
              "max": "100",
              "position": "LEFT",
              "queryIds": [
                "A"
              ],
              "defaultAxis": true
            }
          ]
        },
        "heatmapSettings": {
          "yAxis": "VALUE"
        },
        "thresholds": [
          {
            "axisTarget": "LEFT",
            "rules": [
              {
                "value": 0,
                "color": "#7dc540"
              },
              {
                "value": 80,
                "color": "#f5d30f"
              },
              {
                "value": 90,
                "color": "#dc172a"
              }
            ],
            "queryId": "",
            "visible": true
          }
        ],
        "tableSettings": {
          "isThresholdBackgroundAppliedToCell": false
        },
        "graphChartSettings": {
          "connectNulls": false
        },
        "honeycombSettings": {
          "showHive": true,
          "showLegend": true,
          "showLabels": false
        }
      },
      "queriesSettings": {
        "resolution": ""
      },
      "metricExpressions": [
        "resolution=null&(cloud.gcp.compute_googleapis_com.instance.cpu.utilization:splitBy(\"gcp.instance.name\"):sort(value(auto,descending)):limit(100)):limit(100):names"
      ]
    },
    {
      "name": "CPU utilization",
      "tileType": "DATA_EXPLORER",
      "configured": true,
      "bounds": {
        "top": 304,
        "left": 0,
        "width": 684,
        "height": 304
      },
      "tileFilter": {},
      "customName": "Data explorer results",
      "queries": [
        {
          "id": "A",
          "metric": "cloud.gcp.compute_googleapis_com.instance.cpu.utilization",
          "timeAggregation": "DEFAULT",
          "splitBy": [
            "gcp.instance.name"
          ],
          "sortBy": "DESC",
          "filterBy": {
            "nestedFilters": [],
            "criteria": []
          },
          "limit": 100,
          "enabled": true
        }
      ],
      "visualConfig": {
        "type": "HONEYCOMB",
        "global": {
          "hideLegend": false
        },
        "rules": [
          {
            "matcher": "A:",
            "properties": {
              "color": "DEFAULT"
            },
            "seriesOverrides": []
          }
        ],
        "axes": {
          "xAxis": {
            "displayName": "",
            "visible": true
          },
          "yAxes": [
            {
              "displayName": "",
              "visible": true,
              "min": "0",
              "max": "100",
              "position": "LEFT",
              "queryIds": [
                "A"
              ],
              "defaultAxis": true
            }
          ]
        },
        "heatmapSettings": {
          "yAxis": "VALUE"
        },
        "thresholds": [
          {
            "axisTarget": "LEFT",
            "rules": [
              {
                "value": 0,
                "color": "#7dc540"
              },
              {
                "value": 80,
                "color": "#f5d30f"
              },
              {
                "value": 90,
                "color": "#dc172a"
              }
            ],
            "queryId": "",
            "visible": true
          }
        ],
        "tableSettings": {
          "isThresholdBackgroundAppliedToCell": false
        },
        "graphChartSettings": {
          "connectNulls": false
        },
        "honeycombSettings": {
          "showHive": true,
          "showLegend": true,
          "showLabels": true
        }
      },
      "queriesSettings": {
        "resolution": ""
      },
      "metricExpressions": [
        "resolution=Inf&(cloud.gcp.compute_googleapis_com.instance.cpu.utilization:splitBy(\"gcp.instance.name\"):sort(value(auto,descending)):limit(100)):names"
      ]
    },
    {
      "name": "Total VM's",
      "tileType": "DATA_EXPLORER",
      "configured": true,
      "bounds": {
        "top": 0,
        "left": 0,
        "width": 456,
        "height": 304
      },
      "tileFilter": {},
      "customName": "Data explorer results",
      "queries": [
        {
          "id": "A",
          "timeAggregation": "DEFAULT",
          "splitBy": [
            "gcp.resource.type"
          ],
          "metricSelector": "cloud.gcp.compute_googleapis_com.instance.cpu.utilization:last:count:splitBy(\"gcp.resource.type\")",
          "enabled": true
        }
      ],
      "visualConfig": {
        "type": "SINGLE_VALUE",
        "global": {
          "hideLegend": false
        },
        "rules": [
          {
            "matcher": "A:",
            "properties": {
              "color": "DEFAULT"
            },
            "seriesOverrides": []
          }
        ],
        "axes": {
          "xAxis": {
            "visible": true
          },
          "yAxes": []
        },
        "heatmapSettings": {
          "yAxis": "VALUE"
        },
        "singleValueSettings": {
          "showTrend": false,
          "showSparkLine": false,
          "linkTileColorToThreshold": false
        },
        "thresholds": [
          {
            "axisTarget": "LEFT",
            "columnId": "CPU utilization",
            "rules": [
              {
                "color": "#7dc540"
              },
              {
                "color": "#f5d30f"
              },
              {
                "color": "#dc172a"
              }
            ],
            "queryId": "A",
            "visible": true
          }
        ],
        "tableSettings": {
          "isThresholdBackgroundAppliedToCell": false
        },
        "graphChartSettings": {
          "connectNulls": false
        },
        "honeycombSettings": {
          "showHive": true,
          "showLegend": true,
          "showLabels": false
        }
      },
      "queriesSettings": {
        "resolution": ""
      },
      "metricExpressions": [
        "resolution=null&(cloud.gcp.compute_googleapis_com.instance.cpu.utilization:last:count:splitBy(\"gcp.resource.type\")):limit(100):names:fold(auto)"
      ]
    },
    {
      "name": "VM's by availability zone",
      "tileType": "DATA_EXPLORER",
      "configured": true,
      "bounds": {
        "top": 0,
        "left": 912,
        "width": 456,
        "height": 304
      },
      "tileFilter": {},
      "customName": "Data explorer results",
      "queries": [
        {
          "id": "A",
          "timeAggregation": "DEFAULT",
          "splitBy": [
            "gcp.region"
          ],
          "metricSelector": "cloud.gcp.compute_googleapis_com.instance.cpu.utilization:last:count:splitBy(\"gcp.region\")",
          "enabled": true
        }
      ],
      "visualConfig": {
        "type": "PIE_CHART",
        "global": {
          "hideLegend": false
        },
        "rules": [
          {
            "matcher": "A:",
            "properties": {
              "color": "DEFAULT"
            },
            "seriesOverrides": []
          }
        ],
        "axes": {
          "xAxis": {
            "visible": true
          },
          "yAxes": []
        },
        "heatmapSettings": {
          "yAxis": "VALUE"
        },
        "thresholds": [
          {
            "axisTarget": "LEFT",
            "columnId": "CPU utilization",
            "rules": [
              {
                "value": 0,
                "color": "#7dc540"
              },
              {
                "value": 80,
                "color": "#f5d30f"
              },
              {
                "value": 90,
                "color": "#dc172a"
              }
            ],
            "queryId": "A",
            "visible": true
          }
        ],
        "tableSettings": {
          "isThresholdBackgroundAppliedToCell": false
        },
        "graphChartSettings": {
          "connectNulls": false
        },
        "honeycombSettings": {
          "showHive": true,
          "showLegend": true,
          "showLabels": true
        }
      },
      "queriesSettings": {
        "resolution": ""
      },
      "metricExpressions": [
        "resolution=null&(cloud.gcp.compute_googleapis_com.instance.cpu.utilization:last:count:splitBy(\"gcp.region\")):limit(100):names:fold(auto)"
      ]
    },
    {
      "name": "VM's by project",
      "tileType": "DATA_EXPLORER",
      "configured": true,
      "bounds": {
        "top": 0,
        "left": 456,
        "width": 456,
        "height": 304
      },
      "tileFilter": {},
      "customName": "Data explorer results",
      "queries": [
        {
          "id": "A",
          "timeAggregation": "DEFAULT",
          "splitBy": [
            "gcp.project.id"
          ],
          "metricSelector": "cloud.gcp.compute_googleapis_com.instance.cpu.utilization:last:count:splitBy(\"gcp.project.id\")",
          "enabled": true
        }
      ],
      "visualConfig": {
        "type": "PIE_CHART",
        "global": {
          "hideLegend": false
        },
        "rules": [
          {
            "matcher": "A:",
            "properties": {
              "color": "DEFAULT"
            },
            "seriesOverrides": []
          }
        ],
        "axes": {
          "xAxis": {
            "visible": true
          },
          "yAxes": []
        },
        "heatmapSettings": {
          "yAxis": "VALUE"
        },
        "thresholds": [
          {
            "axisTarget": "LEFT",
            "columnId": "CPU utilization",
            "rules": [
              {
                "value": 0,
                "color": "#7dc540"
              },
              {
                "value": 80,
                "color": "#f5d30f"
              },
              {
                "value": 90,
                "color": "#dc172a"
              }
            ],
            "queryId": "A",
            "visible": true
          }
        ],
        "tableSettings": {
          "isThresholdBackgroundAppliedToCell": false
        },
        "graphChartSettings": {
          "connectNulls": false
        },
        "honeycombSettings": {
          "showHive": true,
          "showLegend": true,
          "showLabels": true
        }
      },
      "queriesSettings": {
        "resolution": ""
      },
      "metricExpressions": [
        "resolution=null&(cloud.gcp.compute_googleapis_com.instance.cpu.utilization:last:count:splitBy(\"gcp.project.id\")):limit(100):names:fold(auto)"
      ]
    }
  ]
}
```

####  7. Build Your developer certificate

Follow the guide
[Sign extensions](https://www.dynatrace.com/support/help/extend-dynatrace/extensions20/sign-extension) to build developer key and **upload** the root certificate to Dynatrace cluster

Build the root certificate
```
openssl genrsa -out root.key 2048 && openssl req -new -key root.key -out root.csr &&  printf YmFzaWNDb25zdHJhaW50cz1jcml0aWNhbCwgQ0E6dHJ1ZSwgcGF0aGxlbjowDQpzdWJqZWN0S2V5SWRlbnRpZmllciAgICA9IGhhc2gNCmF1dGhvcml0eUtleUlkZW50aWZpZXIgID0ga2V5aWQ6YWx3YXlzDQprZXlVc2FnZSAgICAgICAgICAgICAgICA9IGtleUNlcnRTaWdu | base64 -d > ca.txt && openssl x509 -req -days 10000 -in root.csr -signkey root.key -out root.pem -extfile ca.txt
```

Add root certificate to Dynatrace credential vault 

Create developer certificate 
```
openssl genrsa -out developer.key 2048 && openssl req -new -key developer.key -out developer.csr && printf c3ViamVjdEtleUlkZW50aWZpZXIgICAgPSBoYXNoDQphdXRob3JpdHlLZXlJZGVudGlmaWVyICA9IGtleWlkOmFsd2F5cw0Ka2V5VXNhZ2UgICAgICAgICAgICAgICAgPSBkaWdpdGFsU2lnbmF0dXJl | base64 -d > developer.txt && openssl x509 -req -days 10000 -in developer.csr -CA root.pem -CAkey root.key -CAcreateserial -out developer.pem -extfile developer.txt
```


####  7. Clean-up previos extension files & build Your custom extension
```
rm *.zip
rm *.sig*
cd extension
zip -r ../extension.zip *
cd ..
```

#### 8. Sign the extension and create extension archive
```
openssl cms -sign -signer developer.pem -inkey developer.key -binary -in extension.zip -outform PEM -out extension.zip.sig
zip -r google-custom-gce.zip  extension.zip*
```

#### 9. Upload the extension
In Dynatrace UI go to `Infrastructure -> Extensions` , select `Upload custom Extension 2.0` and upload `google-custom-gce.zip` extension.

As result extension should be shown as active with version `0.0.1`

You can double check if `Google Compute Engine` dashboard included into new extension is visible in the Dashboard list in Dynatrace UI.

#### 10. Activate configuration
The custom extension contains metrics for `gce_instance` service and `default_metrics` feature set. You should make sure that this featureSet is activated. 

Follow the guide [Set up the Dynatrace GCP metric integration on a GKE cluster](https://www.dynatrace.com/support/help/how-to-use-dynatrace/infrastructure-monitoring/cloud-platform-monitoring/google-cloud-platform-monitoring/alternative-deployment-scenarios/set-up-gcp-integration-metrics-only)

And make sure You that  `gce_instance`.`default_metrics` is enabled in `values.yaml`. If not , please add it and upgrade helm release.