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

from lib.metric_ingest import *


def test_create_dimension_correct_values():
    name = "n" * (MAX_DIMENSION_NAME_LENGTH - 1)
    value = "v" * (MAX_DIMENSION_VALUE_LENGTH - 1)

    dimension_value = create_dimension(name, value)

    assert dimension_value.name == name
    assert dimension_value.value == value


def test_create_dimension_too_long_dimension():
    name = "n" * (MAX_DIMENSION_NAME_LENGTH + 100)
    value = "v" * (MAX_DIMENSION_VALUE_LENGTH + 100)

    dimension_value = create_dimension(name, value)

    assert len(dimension_value.name) == MAX_DIMENSION_NAME_LENGTH
    assert len(dimension_value.value) == MAX_DIMENSION_VALUE_LENGTH
