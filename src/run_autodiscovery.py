import asyncio
import json
import os
import re
from lib.clientsession_provider import init_gcp_client_session
from lib.context import LoggingContext
from lib.credentials import create_token
from lib.metrics import Metric

logging_context = LoggingContext(None)
projectID="dynatrace-gcp-extension"
discovered_resource_type="cloud_function"

extension_to_gcp_identifires = {"Firebase": ["firebasehosting","firebasedatabase"]}


def unit_caster(unit: str) -> str:
    if unit in ["1","count","Count", "{operation}","{packet}" ,"{packets}" ,"{request}" ,"{port}" ,"{connection}", "{devices}" ,"{errors}" ,"{cpu}", "{query}", "{inode}"]:
        return "Count"
    elif unit == "s" or unit =="s{idle}" or unit == "sec":
        return "Second"
    elif unit == "By" or unit == "Byte" or unit == "bytes":
        return "Byte"
    elif unit == "By/s":
        return "BytePerSecond"
    elif unit == "kBy":
        return "KiloBytePerSecond"
    elif unit == "GBy.s":
        return "GigaBytePerSecond"
    elif unit == "GiBy" or unit == "GBy":
        return "GigaByte"
    elif unit == "MiBy":
        return "MegaByte"
    elif unit == "ns":
        return "NanoSecond"
    elif unit == "us" or unit == "usec":
        return "MicroSecond"
    elif unit == "ms" or unit == "milliseconds":
        return "MilliSecond"
    elif unit == "us{CPU}":
        return "MicroSecond"
    elif unit == "10^2.%":
        return "Percent"
    elif unit == "%":
        return "Percent"
    elif unit == "percent":
        return "Percent"
    elif unit == "1/s":
        return "PerSecond"
    elif unit == "frames/seconds":
        return "PerSecond"
    elif unit == "s{CPU}":
        return "Second"
    elif unit == "s{uptime}":
        return "Second"
    elif unit == "{dBm}":
        return "DecibelMilliWatt"
    else:
        return "Unspecified"
    

def type_metrickind_caster(metrickind: str, valuetype: str) -> str:
    if metrickind == "GAUGE":
        return "gauge"
    if metrickind == "DELTA" and valuetype == "DISTRIBUTION":
        return "gauge"
    if metrickind == "DELTA" and valuetype != "DISTRIBUTION":
        return "count,delta"
    else:
        return ""

    
def name_parse(name: str) -> str:
   # . -> _
   # / -> .
   out = re.sub(r'\.','_',name)
   fin = re.sub(r'/','.',out)
   return fin

async def init_session():
    async with init_gcp_client_session() as gcp_session:
        token = await create_token(logging_context, gcp_session)
        if token:
            await get_metric_descriptors(gcp_session,token)
        else:
            logging_context.log(f'Unable to acquire authorization token.')


async def get_metric_descriptors(gcp_session,token):
    headers = {
    "Accept": "application/json",
    "Authorization": f"Bearer {token}"}
    url = f"https://monitoring.googleapis.com/v3/projects/{projectID}/metricDescriptors"
    resp = await gcp_session.request('GET', url=url, headers=headers)
    page = await resp.json()
    with open('metricDescriptors.json', 'w') as f:
        json.dump(page, f,indent=4)

    metric_yaml = [
        {
            "value": x.get("type"),
            "key":  "cloud.gcp." + name_parse(x.get("type")),
            "displayName":  x.get("displayName"),
            "name": x.get("displayName"),
            "type": type_metrickind_caster(x.get("metricKind"),x.get("valueType")),
            "gcpOptions":
                {
                    "ingestDelay":  int(x.get("metadata",{}).get("ingestDelay","60s")[:-1]),
                    "samplePeriod": int(x.get("metadata",{}).get("samplePeriod","60s")[:-1]),
                    "valueType":    x.get("valueType"),
                    "metricKind":   x.get("metricKind"),
                    "unit":         unit_caster(x.get("unit"))
            },
            "dimensions": [ 
                {
                "key":      dimension.get("key"), 
                "value":    "label:metric.labels." + dimension.get("key"),
                } for dimension in x.get("labels") or []],
            "monitored_resources_types": x.get("monitoredResourceTypes",[])
        } for x in page["metricDescriptors"]]
    
  

    metric_list = [(Metric(**x), x.get("monitored_resources_types")) for x in metric_yaml]
    discovered_resource_type_list = list(filter(lambda x: discovered_resource_type in x[1], metric_list))
    return discovered_resource_type_list


async def enrich_services_autodiscovery(gcp_services_list,gcp_session,token):
    print("Start AutoDiscovery")


    bucket_gcp_services =  list(filter(lambda x: discovered_resource_type in x.name, gcp_services_list[0]))
    existing_metric_list = [metric for service in bucket_gcp_services for metric in service.metrics]
    all_metrics_list = await get_metric_descriptors(gcp_session,token)


    missing_metrics_list = [metric[0] for metric in all_metrics_list if metric[0].google_metric not in [existing_metric.google_metric for existing_metric in existing_metric_list]]


    print(f"In Extension we have this amount of metrics: {len(existing_metric_list)}" )
    print(f"Resource type: {discovered_resource_type} have this amount of metrics: {len(all_metrics_list)}" )
    print(f"Adding {len(missing_metrics_list)} metrics")
    print(f"Adding metrics: [{[metric.google_metric for metric in missing_metrics_list]}]")

    for service in gcp_services_list[0]:
            if service.name == discovered_resource_type:
                service.metrics.extend(missing_metrics_list)
    
    
    return gcp_services_list




def main():
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\Users\szymon.nagel\Downloads\dynatrace-gcp-extension-0618ff31e584.json"
    logging_context.log("Dynatrace GCP Metrics autodiscovery startup")
    asyncio.run(init_session())

if __name__ == '__main__':
    main()
