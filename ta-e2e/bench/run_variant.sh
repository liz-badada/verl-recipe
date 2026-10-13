#!/bin/bash
# run_variant.sh <ta-subagent|ta-main|kv-router|round-robin>
set -uo pipefail
V=$1; MODEL=Qwen/Qwen2.5-0.5B-Instruct
OUT=/e2e/bench/results/$V; LOGS=$OUT/logs; mkdir -p $LOGS; rm -f $LOGS/*.log $OUT/*.json
B=/e2e/bench
stop_all() { pkill -9 -f 'etcd --data-dir|nats-server|python -m dynamo\.' 2>/dev/null; sleep 2; rm -rf /tmp/etcd /tmp/nats; }
cleanup() { pkill -P $$ 2>/dev/null; sleep 1; stop_all; }; trap cleanup EXIT
stop_all
etcd --data-dir /tmp/etcd --listen-client-urls http://127.0.0.1:2379 --advertise-client-urls http://127.0.0.1:2379 > $LOGS/etcd.log 2>&1 &
nats-server -js -m 8222 -sd /tmp/nats > $LOGS/nats.log 2>&1 &
for i in $(seq 1 30); do curl -s -m 2 http://127.0.0.1:2379/health 2>/dev/null | grep -q '"health":"true"' && curl -s -m 2 http://127.0.0.1:8222/healthz >/dev/null 2>&1 && break; sleep 1; done
echo "[$V] etcd: $(curl -s -m 2 http://127.0.0.1:2379/health) nats: $(curl -s -m 2 -o /dev/null -w '%{http_code}' http://127.0.0.1:8222/healthz)"
case $V in
  ta-subagent|ta-main)
    [ $V = ta-subagent ] && export PYTHONPATH=/src || export PYTHONPATH=/src-main
    python -m dynamo.frontend --http-port 8801 --router-mode round-robin > $LOGS/frontend.log 2>&1 &
    python -m dynamo.mocker --model-path $MODEL --model-name "$MODEL--backend" --endpoint dyn://dynamo.backend.generate \
      --num-workers 2 --speedup-ratio 1 --block-size 16 --num-gpu-blocks-override ${BLOCKS:-2048} > $LOGS/mocker.log 2>&1 &
    sleep 20
    python -m dynamo.thunderagent_router --endpoint dynamo.backend.generate --model-name $MODEL --model-path $MODEL --router-block-size 16 > $LOGS/router.log 2>&1 &
    ;;
  kv-router|round-robin)
    export PYTHONPATH=/src
    MODE=$V; [ $V = kv-router ] && MODE=kv
    python -m dynamo.frontend --http-port 8801 --router-mode $MODE --kv-cache-block-size 16 > $LOGS/frontend.log 2>&1 &
    python -m dynamo.mocker --model-path $MODEL --model-name "$MODEL" --endpoint dyn://dynamo.backend.generate \
      --num-workers 2 --speedup-ratio 1 --block-size 16 --num-gpu-blocks-override ${BLOCKS:-2048} > $LOGS/mocker.log 2>&1 &
    ;;
esac
for i in $(seq 1 90); do curl -s -m 3 http://127.0.0.1:8801/v1/models 2>/dev/null | grep -q "\"$MODEL\"" && break; sleep 2; done
sleep 5
echo "[$V] models: $(curl -s -m 5 http://127.0.0.1:8801/v1/models | python -c 'import sys,json; print([m["id"] for m in json.load(sys.stdin)["data"]])')"
python $B/frontend_metrics.py > $OUT/frontend_before.json
[ ${V%%-*} = ta ] && (python $B/router_metrics.py > $OUT/router_before.json 2> $LOGS/router_metrics_before.err || echo "[$V] router metrics unavailable")
python $B/subagent_load.py --model $MODEL --sessions ${SESSIONS:-24} --subagents ${SUBAGENTS:-3} --turns ${TURNS:-3} --concurrency ${CONC:-8} --out $OUT/load.json --request-timeout ${REQ_TIMEOUT:-180} | sed "s/^/[$V] load: /"
sleep 3
python $B/frontend_metrics.py > $OUT/frontend_after.json
[ ${V%%-*} = ta ] && (python $B/router_metrics.py > $OUT/router_after.json 2> $LOGS/router_metrics_after.err || echo "[$V] router metrics unavailable")
echo "[$V] frontend: before=$(cat $OUT/frontend_before.json) after=$(cat $OUT/frontend_after.json)"
[ ${V%%-*} = ta ] && echo "[$V] router program log: created=$(grep -c 'thunderagent.program created' $LOGS/router.log) terminated=$(grep -c 'thunderagent.program terminated' $LOGS/router.log) paused=$(grep -c 'thunderagent.program paused' $LOGS/router.log) resumed=$(grep -c 'thunderagent.program resumed' $LOGS/router.log) released_sum=$(grep -o 'released=[0-9]*' $LOGS/router.log | awk -F= '{s+=$2} END {print s+0}')"
echo "[$V] errors in logs: $(grep -ciE 'error|traceback' $LOGS/router.log $LOGS/mocker.log 2>/dev/null | tr '\n' ' ')"
