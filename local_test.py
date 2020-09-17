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
