#!/bin/bash
# smoke_dynamo.sh: inside the trainer image on one GPU, bring up etcd + nats + dynamo.frontend
# (KV router + native ThunderAgent policy) + one dynamo.vllm worker on vLLM 0.24, then send a
# small subagent tree with session / parent / final headers and show what the plugin logged.
set -uo pipefail
MODEL=${MODEL:-/models/Qwen2.5-0.5B-Instruct}; PORT=${PORT:-8811}; L=${LOGDIR:-/tmp/smoke}; mkdir -p $L
cleanup() { pkill -P $$ 2>/dev/null; sleep 1; pkill -9 -P $$ 2>/dev/null; }; trap cleanup EXIT
etcd --data-dir $L/etcd --listen-client-urls http://127.0.0.1:2389 --advertise-client-urls http://127.0.0.1:2389 --listen-peer-urls http://127.0.0.1:2390 > $L/etcd.log 2>&1 &
nats-server -js -p 4232 -m 8232 -sd $L/nats > $L/nats.log 2>&1 &
export ETCD_ENDPOINTS=http://127.0.0.1:2389 NATS_SERVER=nats://127.0.0.1:4232 DYN_LOG='info,thunderagent=debug'
sleep 2
cat > $L/thunderagent.yaml <<'Y'
request_classifier:
  type: thunderagent
  parameters:
    scheduler_interval_seconds: 1
worker_selection:
  aggregated: thunderagent
  instances:
    - name: thunderagent
      type: thunderagent
Y
python -m dynamo.frontend --http-port $PORT --router-mode kv --kv-cache-block-size 16 --router-policy-config $L/thunderagent.yaml \
  --router-session-affinity-ttl-secs 1800 --router-session-affinity-mode soft > $L/frontend.log 2>&1 &
DYN_SYSTEM_PORT=8181 python -m dynamo.vllm --model $MODEL --gpu-memory-utilization 0.3 --block-size 16 --max-model-len 8192 --enforce-eager \
  --kv-events-config '{"publisher":"zmq","topic":"kv-events","endpoint":"tcp://*:20099","enable_kv_cache_events":true}' > $L/vllm.log 2>&1 &
for i in $(seq 1 90); do curl -s -m 3 http://127.0.0.1:$PORT/v1/models 2>/dev/null | grep -q "$MODEL" && break; sleep 3; done
echo "models: $(curl -s -m 5 http://127.0.0.1:$PORT/v1/models | head -c 300)"
req() { curl -s -m 120 http://127.0.0.1:$PORT/v1/completions -H 'Content-Type: application/json' "$@" | head -c 200; echo; }
req -H 'X-Dynamo-Session-ID: root' -d "{\"model\":\"$MODEL\",\"prompt\":\"Root agent turn one.\",\"max_tokens\":8}"
req -H 'X-Dynamo-Session-ID: sub-a' -H 'X-Dynamo-Parent-Session-ID: root' -d "{\"model\":\"$MODEL\",\"prompt\":\"Subagent a turn one.\",\"max_tokens\":8}"
req -H 'X-Dynamo-Session-ID: sub-b' -H 'X-Dynamo-Parent-Session-ID: root' -d "{\"model\":\"$MODEL\",\"prompt\":\"Subagent b turn one.\",\"max_tokens\":8}"
req -H 'X-Dynamo-Session-ID: sub-a' -H 'X-Dynamo-Session-Final: true' -d "{\"model\":\"$MODEL\",\"prompt\":[0],\"max_tokens\":1}"
req -H 'X-Dynamo-Session-ID: root' -d "{\"model\":\"$MODEL\",\"prompt\":\"Root agent turn two.\",\"max_tokens\":8}"
req -H 'X-Dynamo-Session-ID: root' -H 'X-Dynamo-Session-Final: true' -d "{\"model\":\"$MODEL\",\"prompt\":[0],\"max_tokens\":1}"
sleep 3
echo "--- frontend thunderagent log lines:"; grep -i -E 'thunderagent|policy|classifier' $L/frontend.log | head -30
echo "--- worker errors:"; grep -i -E 'error|traceback' $L/vllm.log | head -5
echo "--- frontend metrics (thunderagent / router):"; curl -s -m 5 http://127.0.0.1:$PORT/metrics | grep -i -E 'thunder|program|policy' | head -20
