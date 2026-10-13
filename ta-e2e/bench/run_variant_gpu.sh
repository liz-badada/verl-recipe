#!/bin/bash
# run_variant_gpu.sh <ta-subagent|ta-main|kv-router|round-robin>: same load as run_variant.sh,
# but with two real vLLM workers (dynamo.vllm) sharing one GPU instead of dynamo.mocker.
set -uo pipefail
V=$1; MODEL=${MODEL:-Qwen/Qwen2.5-0.5B-Instruct}
OUT=/e2e/bench/${RESULTS:-results-gpu}/$V; LOGS=$OUT/logs; mkdir -p $LOGS; rm -f $LOGS/*.log $OUT/*.json
B=/e2e/bench
cleanup() { pkill -P $$ 2>/dev/null; sleep 2; pkill -9 -P $$ 2>/dev/null; }; trap cleanup EXIT
etcd --data-dir /tmp/etcd --listen-client-urls http://127.0.0.1:2379 --advertise-client-urls http://127.0.0.1:2379 > $LOGS/etcd.log 2>&1 &
nats-server -js -m 8222 -sd /tmp/nats > $LOGS/nats.log 2>&1 &
for i in $(seq 1 30); do curl -s -m 2 http://127.0.0.1:2379/health 2>/dev/null | grep -q '"health":"true"' && break; sleep 1; done
# FlashInfer's top-k/top-p sampler JIT-compiles with nvcc, which this image lacks; vLLM's native sampler is fine here.
export VLLM_USE_FLASHINFER_SAMPLER=0
# Two workers racing on the same HF cache trip the download lock: fetch once, up front.
python -c "from huggingface_hub import snapshot_download; snapshot_download('$MODEL')" > $LOGS/download.log 2>&1
WORKER_ARGS="--model $MODEL --gpu-memory-utilization ${GPU_MEM:-0.30} ${BLOCKS:+--num-gpu-blocks-override $BLOCKS} --block-size 16 --max-model-len ${MAX_MODEL_LEN:-8192} --enforce-eager --max-num-seqs ${MAX_NUM_SEQS:-64}"
case $V in
  ta-subagent|ta-main|ta-subagent-tuned)
    [ $V = ta-main ] && export PYTHONPATH=/src-main || export PYTHONPATH=/src
    python -m dynamo.frontend --http-port 8801 --router-mode round-robin > $LOGS/frontend.log 2>&1 &
    for w in 0 1; do
      CUDA_VISIBLE_DEVICES=${PER_GPU:+$w} DYN_SYSTEM_PORT=$((8081+w)) python -m dynamo.vllm $WORKER_ARGS --endpoint-types none \
        --kv-events-config "{\"publisher\":\"zmq\",\"topic\":\"kv-events\",\"endpoint\":\"tcp://*:$((20080+w))\",\"enable_kv_cache_events\":true}" \
        > $LOGS/vllm$w.log 2>&1 &
    done
    for i in $(seq 1 120); do [ "$(grep -c 'Serving endpoint\|serving endpoint\|Starting to serve' $LOGS/vllm0.log $LOGS/vllm1.log 2>/dev/null | awk -F: '{s+=$2} END{print s+0}')" -ge 2 ] && break; sleep 5; done
    python -m dynamo.thunderagent_router --endpoint dynamo.backend.generate --model-name $MODEL --model-path $MODEL --router-block-size 16 ${TA_ARGS:-} > $LOGS/router.log 2>&1 &
    ;;
  kv-router|round-robin)
    export PYTHONPATH=/src
    MODE=$V; [ $V = kv-router ] && MODE=kv
    python -m dynamo.frontend --http-port 8801 --router-mode $MODE --kv-cache-block-size 16 > $LOGS/frontend.log 2>&1 &
    for w in 0 1; do
      CUDA_VISIBLE_DEVICES=${PER_GPU:+$w} DYN_SYSTEM_PORT=$((8081+w)) python -m dynamo.vllm $WORKER_ARGS \
        --kv-events-config "{\"publisher\":\"zmq\",\"topic\":\"kv-events\",\"endpoint\":\"tcp://*:$((20080+w))\",\"enable_kv_cache_events\":true}" \
        > $LOGS/vllm$w.log 2>&1 &
    done
    ;;
esac
for i in $(seq 1 150); do curl -s -m 3 http://127.0.0.1:8801/v1/models 2>/dev/null | grep -q "\"$MODEL\"" && break; sleep 4; done
sleep 10
echo "[$V] models: $(curl -s -m 5 http://127.0.0.1:8801/v1/models | python -c 'import sys,json; print([m["id"] for m in json.load(sys.stdin)["data"]])' 2>&1)"
echo "[$V] workers ready: $(grep -l 'Serving endpoint\|serving endpoint\|Starting to serve' $LOGS/vllm*.log 2>/dev/null | wc -l)"
# warm-up: one short request so the first-request compile cost is not in the window
curl -s -m 120 http://127.0.0.1:8801/v1/chat/completions -H 'Content-Type: application/json' -H 'x-dynamo-session-id: warm' -H 'x-dynamo-session-final: true' \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":4}" > /dev/null
python $B/frontend_metrics.py > $OUT/frontend_before.json
for w in 0 1; do curl -s -m 5 http://127.0.0.1:$((8081+w))/metrics | grep -E "^vllm:prefix_cache_(queries|hits)_total" > $OUT/vllm${w}_before.prom; done
[ ${V%%-*} = ta ] && (python $B/router_metrics.py > $OUT/router_before.json 2> $LOGS/router_metrics_before.err || echo "[$V] router metrics unavailable")
if [ -n "${GATEWAY_URL:-}" ]; then
  # Gateway variant: the recipe's real adapter names programs and releases returned subagents.
  for i in $(seq 1 90); do curl -s -m 3 $GATEWAY_URL/control/stats >/dev/null 2>&1 && break; sleep 2; done
  echo "[$V] gateway: $(curl -s -m 5 $GATEWAY_URL/control/stats)"
  python $B/../gw/subagent_load_gw.py --gateway $GATEWAY_URL --model $MODEL --sessions ${SESSIONS:-48} --subagents ${SUBAGENTS:-3} --turns ${TURNS:-3} --concurrency ${CONC:-12} --out $OUT/load.json --request-timeout ${REQ_TIMEOUT:-120} --root-sys ${ROOT_SYS:-1500} --sub-sys ${SUB_SYS:-1200} --task ${TASK:-200} --tool ${TOOL:-300} --max-tokens ${MAX_TOKENS:-48} --root-turns ${ROOT_TURNS:-1} --tool-gap-s ${TOOL_GAP:-0} | sed "s/^/[$V] load: /"
else
python $B/subagent_load.py --model $MODEL --sessions ${SESSIONS:-48} --subagents ${SUBAGENTS:-3} --turns ${TURNS:-3} --concurrency ${CONC:-12} --out $OUT/load.json --request-timeout ${REQ_TIMEOUT:-120} --root-sys ${ROOT_SYS:-1500} --sub-sys ${SUB_SYS:-1200} --task ${TASK:-200} --tool ${TOOL:-300} --max-tokens ${MAX_TOKENS:-48} --root-turns ${ROOT_TURNS:-1} --tool-gap-s ${TOOL_GAP:-0} ${RELEASE_RETURNED:+--release-returned-subagents} | sed "s/^/[$V] load: /"
fi
sleep 3
python $B/frontend_metrics.py > $OUT/frontend_after.json
for w in 0 1; do curl -s -m 5 http://127.0.0.1:$((8081+w))/metrics | grep -E "^vllm:prefix_cache_(queries|hits)_total" > $OUT/vllm${w}_after.prom; done
[ ${V%%-*} = ta ] && (python $B/router_metrics.py > $OUT/router_after.json 2> $LOGS/router_metrics_after.err || echo "[$V] router metrics unavailable")
echo "[$V] frontend: before=$(cat $OUT/frontend_before.json) after=$(cat $OUT/frontend_after.json)"
echo "[$V] vllm prefix: $(cat $OUT/vllm*_after.prom | tr '\n' ' ')"
[ ${V%%-*} = ta ] && echo "[$V] router program log: created=$(grep -c 'thunderagent.program created' $LOGS/router.log) terminated=$(grep -c 'thunderagent.program terminated' $LOGS/router.log) paused=$(grep -c 'thunderagent.program paused' $LOGS/router.log) resumed=$(grep -c 'thunderagent.program resumed' $LOGS/router.log)"
echo "[$V] errors in logs: $(grep -ciE 'error|traceback' $LOGS/router.log $LOGS/vllm0.log $LOGS/vllm1.log 2>/dev/null | tr '\n' ' ')"
