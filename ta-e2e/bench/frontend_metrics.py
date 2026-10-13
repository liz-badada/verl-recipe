"""Reduce the frontend's Prometheus text to the counters the benchmark reads."""
import json, re, sys, urllib.request

text = urllib.request.urlopen("http://127.0.0.1:8801/metrics", timeout=10).read().decode()
out = {}
for name in ("dynamo_frontend_cached_tokens_sum", "dynamo_frontend_cached_tokens_count",
             "dynamo_frontend_input_sequence_tokens_sum", "dynamo_frontend_requests_total",
             "dynamo_frontend_request_duration_seconds_sum"):
    total = 0.0
    for m in re.finditer(rf"^{name}\{{([^}}]*)\}} ([0-9.eE+-]+)$", text, re.M):
        if '--backend' in m.group(1):
            continue
        total += float(m.group(2))
    out[name] = total
print(json.dumps(out))
