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

import time
from datetime import datetime

from main import dynatrace_gcp_extension

timestamp_utc = datetime.utcnow()
timestamp_utc_iso = timestamp_utc.isoformat()
context = {'timestamp': timestamp_utc_iso, 'event_id': timestamp_utc.timestamp(), 'event_type': 'test'}
data = {'data': '', 'publishTime': timestamp_utc_iso}

start_time = time.time()
dynatrace_gcp_extension(data, context, "dynatrace-gcp-extension")
elapsed_time = time.time() - start_time
print(f"Execution took {elapsed_time}")
