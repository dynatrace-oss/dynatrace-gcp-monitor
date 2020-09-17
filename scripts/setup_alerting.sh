#!/bin/bash

echo "Creating Alerts and Dashboards"

if ! command -v yq &> /dev/null
then
  sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys CC86BB64
  sudo add-apt-repository -y ppa:rmescandon/yq
  sudo apt update
  sudo apt install yq -y
fi

if ! command -v jq &> /dev/null
then
  sudo apt-get install jq -y
fi

for FILEPATH in ../config/*.yaml ../config/*.yml
do
#  echo "Setting up $FILEPATH"

  DASHBOARDS_NUMBER=$(yq r --length "$FILEPATH" dashboards)
  if [ "$DASHBOARDS_NUMBER" != "" ]; then
    MAX_INDEX=-1
    ((MAX_INDEX += DASHBOARDS_NUMBER))
    for INDEX in $(seq 0 "$MAX_INDEX");
    do
      DASHBOARD_PATH=$(yq r -j "$FILEPATH" dashboards[$INDEX].dashboard | tr -d '"')
      DASHBOARD_JSON=$(cat "../$DASHBOARD_PATH")
      echo "- Create $DASHBOARD_PATH dashboard"
      curl -X POST "${DYNATRACE_URL}api/config/v1/dashboards" \
       -H "Accept: application/json; charset=utf-8" \
       -H "Content-Type: application/json; charset=utf-8" \
       -H "Authorization: Api-Token $DYNATRACE_ACCESS_KEY" \
       -d "$DASHBOARD_JSON"
      echo ""
    done
  fi

  ALERTS_NUMBER=$(yq r --length "$FILEPATH" alerting)
  if [ "$ALERTS_NUMBER" != "" ]; then
    MAX_INDEX=-1
    ((MAX_INDEX += ALERTS_NUMBER))
    for INDEX in $(seq 0 "$MAX_INDEX");
    do
      PAYLOAD_JSON=$(yq r -j "$FILEPATH" alerting[$INDEX] | jq -r '{
        name: .name,
        metricId: .query,
        description: .description,
        aggregationType: .aggregationType,
        enabled: true,
        severity: "CUSTOM_ALERT",
        monitoringStrategy: .model,
        metricDimensions: [.metricDimensions]}')
#      echo "$PAYLOAD_JSON"

      echo "- Create $(yq r -j "$FILEPATH" alerting[$INDEX].name) alert "
      curl -X POST "${DYNATRACE_URL}api/config/v1/anomalyDetection/metricEvents" \
       -H "Accept: application/json; charset=utf-8" \
       -H "Content-Type: application/json; charset=utf-8" \
       -H "Authorization: Api-Token $DYNATRACE_ACCESS_KEY" \
       -d "$PAYLOAD_JSON"
      echo ""
    done
  fi
done