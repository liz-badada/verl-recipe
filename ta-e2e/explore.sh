#!/bin/bash
set -uo pipefail
MODEL=Qwen/Qwen2.5-0.5B-Instruct; LOGS=/e2e/logs-explore; mkdir -p $LOGS; rm -f $LOGS/*.log
cleanup() { pkill -P $$ 2>/dev/null; sleep 1; pkill -9 -P $$ 2>/dev/null; }; trap cleanup EXIT
etcd --data-dir /tmp/etcd --listen-client-urls http://127.0.0.1:2379 --advertise-client-urls http://127.0.0.1:2379 > $LOGS/etcd.log 2>&1 &
nats-server -js -sd /tmp/nats > $LOGS/nats.log 2>&1 &
sleep 3
python -m dynamo.frontend --http-port 8801 --router-mode round-robin > $LOGS/frontend.log 2>&1 &
DYN_SYSTEM_PORT=8081 python -m dynamo.mocker --model-path "$MODEL" --model-name "$MODEL--backend" --endpoint dyn://dynamo.backend.generate \
  --num-workers 2 --speedup-ratio 1 --block-size 16 > $LOGS/mocker.log 2>&1 &
sleep 20
python -m dynamo.thunderagent_router --endpoint dynamo.backend.generate --model-name "$MODEL" --model-path "$MODEL" --router-block-size 16 > $LOGS/router.log 2>&1 &
for i in $(seq 1 60); do curl -s -m 3 http://127.0.0.1:8801/v1/models 2>/dev/null | grep -q "\"$MODEL\"" && break; sleep 2; done
python -c "import aiohttp, httpx; print('aiohttp', aiohttp.__version__, 'httpx', httpx.__version__)" 2>&1 | tail -1
for s in a a b; do curl -s -m 60 http://127.0.0.1:8801/v1/chat/completions -H 'Content-Type: application/json' -H "x-dynamo-session-id: s-$s" -H "x-request-id: myreq-$s-$RANDOM" \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"system\",\"content\":\"$(printf 'p%.0s' {1..300})\"},{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":16}" > /dev/null; done
sleep 2
echo "== frontend /metrics (kv/prefix/hit) =="; curl -s -m 5 http://127.0.0.1:8801/metrics | grep -iE "prefix|hit|kvstats|cache" | grep -v "^#" | cut -c1-200 | head -20
echo "== mocker system /metrics =="; curl -s -m 5 http://127.0.0.1:8081/metrics | grep -iE "prefix|hit|kv|cache" | grep -v "^#" | cut -c1-200 | head -20
echo "== x-request-id honoured? =="; grep -c "myreq-" $LOGS/router.log; grep -o "request_id=\"myreq-[^\"]*\"" $LOGS/router.log | head -3
echo "== runtime metrics client =="
python - <<'PY'
import asyncio, json
from dynamo.runtime import DistributedRuntime
async def main():
    rt = DistributedRuntime(asyncio.get_running_loop(), False) if False else None
PY
python - <<'PY'
import asyncio, json, inspect
import dynamo.runtime as r
print([n for n in dir(r) if not n.startswith("_")])
print(inspect.signature(r.DistributedRuntime.__init__) if hasattr(r.DistributedRuntime,'__init__') else '')
PY
