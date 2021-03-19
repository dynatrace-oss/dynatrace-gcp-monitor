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
from lib.context import LoggingContext
from main import load_supported_services

DATA_POINT_WEIGHT = 0.001
DECIMAL_PLACES = 3
ASSUMED_AVG_DIMENSION_VALUES = 3


def generate_ddu_estimation():
    supported_services = load_supported_services(LoggingContext(None), [])

    print("|| Service name || Configuration || DDU per minute per instance ||")

    for supported_service in supported_services:
        data_points_per_minute = 0

        for metric in supported_service.metrics:
            dimensions_multiplier = (ASSUMED_AVG_DIMENSION_VALUES ** len(metric.dimensions))
            rate_per_minute = (metric.sample_period_seconds.seconds / 60.0)
            data_points_per_minute += rate_per_minute * dimensions_multiplier

        ddu_estimation = round(data_points_per_minute * DATA_POINT_WEIGHT, DECIMAL_PLACES)
        data_points_rate_estimation = round(data_points_per_minute, 0)
        feature_set = "/" + supported_service.feature_set

        print(f"| {supported_service.technology_name} | {supported_service.name}{feature_set} | {ddu_estimation} |")

if __name__ == "__main__":
    generate_ddu_estimation()
