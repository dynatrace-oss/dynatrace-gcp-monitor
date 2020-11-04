#     Copyright 2020 Dynatrace LLC
#
#     Licensed under the Apache License, Version 2.0 (the "License");
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.
import json
import re
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Set

from lib.context import LoggingContext
from lib.metrics import Metric
from main import load_supported_services

_UNIT_MAPPING = {
    "s": "Second",
    # "s{CPU}": "Second",
    "us": "MicroSecond",
    "ns": "NanoSecond",
    "ms": "MilliSecond",
    "min": "Minute",
    "h": "Hour",
    "d": "Day",

    "": "Unspecified",
    "1": "Unspecified",
    "count": "Count",
    "1/s": "PerSecond",

    "%": "Percent",
    "10^2.%": "Percent",

    # "By.s": "Byte",
    "By": "Byte",
    "KBy": "KiloByte",
    "KiBy": "KibiByte",
    "MiBy": "MebiByte",
    "MBy": "MegaByte",
    "GiBy": "GibiByte",
    "GBy": "GigaByte",
    "By/s": "BytePerSecond",
}


def generate_metadata():
    toc = []
    units = set()
    unmapped_units = set()
    # some metrics are used for multiple services and script will encounter them multiple times
    visited_metric_keys = set()
    supported_services = load_supported_services(LoggingContext(None), [])

    prepare_metric_metadata_dir()

    for supported_service in supported_services:
        print(f"\n => {supported_service.name}")
        for metric in supported_service.metrics:
            print(f"{metric.dynatrace_name}")
            if metric.dynatrace_name in visited_metric_keys:
                print(" - Already mapped, skipping")
                continue
            else:
                visited_metric_keys.add(metric.dynatrace_name)

            metadata = create_metadata(metric, unmapped_units)

            if not metadata:
                continue

            filename = write_metadata(metadata, metric)

            units.add(metric.unit)
            toc.append(filename)

    write_toc(toc)

    print(f"\nFound units: {units}")
    print(f"\nFailed to map units: {unmapped_units}")


def write_metadata(metadata, metric) -> str:
    filename = metric.dynatrace_name
    if "count" in metric.dynatrace_metric_type and not filename.endswith("count"):
        filename += ".count"
    if "gauge" in metric.dynatrace_metric_type and filename.endswith("count"):
        filename += ".gauge"
    with open(f"metric-metadata/{filename}.json", "a") as metadata_file:
        json.dump(metadata, metadata_file, indent=4)
    return filename


def create_metadata(metric: Metric, unmapped_units: Set[str]) -> Optional[Dict]:
    sanitized_unit = re.sub("\{\\w+\}", "", metric.unit)
    mapped_unit = _UNIT_MAPPING.get(sanitized_unit, None)

    if not mapped_unit:
        print(f"!! FAILED TO MAP UNIT {metric.unit} (sanitized: {sanitized_unit})")
        unmapped_units.add(metric.unit)
        mapped_unit = "Unspecified"

    if metric.dynatrace_name.endswith(metric.name) and mapped_unit == "Unspecified":
        print("! No metadata exists")
        return None

    metadata = {
        "displayName": metric.name,
        "unit": mapped_unit,
        "dimensions": []
    }

    print(metadata)

    return metadata


def write_toc(toc: List[str]):
    with open(f"metric-metadata/metric-key-list.txt", "w") as toc_file:
        for toc_entry in toc:
            toc_file.write(toc_entry + "\n")


def prepare_metric_metadata_dir():
    result_dir = Path("metric-metadata")
    if result_dir.exists():
        shutil.rmtree(result_dir)
    Path.mkdir(result_dir)


generate_metadata()
