#!/bin/bash
# Real dynamo runtime (nightly wheel) + repo thunderagent_router on PYTHONPATH.
# Root -> two parallel subagents -> root final; expect released=3 remaining=0.
set -uo pipefail
MODEL=${MODEL:-Qwen/Qwen2.5-0.5B-Instruct}
LOGS=${LOGS:-/e2e/logs}; mkdir -p "$LOGS"; rm -f "$LOGS"/*.log
cleanup() { pkill -P $$ 2>/dev/null; sleep 1; pkill -9 -P $$ 2>/dev/null; }
trap cleanup EXIT

etcd --data-dir /tmp/etcd --listen-client-urls http://127.0.0.1:2379 --advertise-client-urls http://127.0.0.1:2379 > "$LOGS/etcd.log" 2>&1 &
nats-server -js -sd /tmp/nats > "$LOGS/nats.log" 2>&1 &
sleep 3
python -m dynamo.frontend --http-port 8801 --router-mode round-robin > "$LOGS/frontend.log" 2>&1 &
python -m dynamo.mocker --model-path "$MODEL" --model-name "$MODEL--backend" --endpoint dyn://dynamo.backend.generate \
  --num-workers 2 --speedup-ratio 0 --block-size 16 > "$LOGS/mocker.log" 2>&1 &
for i in $(seq 1 60); do grep -q "ThunderAgent\|Serving\|serving" "$LOGS/mocker.log" 2>/dev/null && break; sleep 2; done
python -m dynamo.thunderagent_router --endpoint dynamo.backend.generate --model-name "$MODEL" --model-path "$MODEL" \
  --router-block-size 16 > "$LOGS/router.log" 2>&1 &
for i in $(seq 1 60); do curl -s -m 3 http://127.0.0.1:8801/v1/models 2>/dev/null | grep -q "\"$MODEL\"" && break; sleep 2; done
echo "== models =="; curl -s -m 5 http://127.0.0.1:8801/v1/models | python -c 'import sys,json; print([m["id"] for m in json.load(sys.stdin)["data"]])'

req() { # $1=session $2=parent-or-empty $3=final-or-empty $4=content
  local h=(-H 'Content-Type: application/json' -H "x-dynamo-session-id: $1")
  [ -n "$2" ] && h+=(-H "x-dynamo-parent-session-id: $2")
  [ -n "$3" ] && h+=(-H "x-dynamo-session-final: true")
  curl -s -m 120 http://127.0.0.1:8801/v1/chat/completions "${h[@]}" \
    -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"system\",\"content\":\"$4\"},{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":8}" | head -c 160; echo
}
echo "== root turn =="; req root-1 "" "" "root system prompt $(printf 'r%.0s' {1..200})"
echo "== two subagents in parallel =="
req sub-a root-1 "" "subagent system prompt $(printf 's%.0s' {1..200})" & p1=$!
req sub-b root-1 "" "subagent system prompt $(printf 's%.0s' {1..200})" & p2=$!
wait $p1 $p2
echo "== subagents second turn =="; req sub-a root-1 "" "subagent system prompt $(printf 's%.0s' {1..200})"; req sub-b root-1 "" "subagent system prompt $(printf 's%.0s' {1..200})"
echo "== root resumes =="; req root-1 "" "" "root system prompt $(printf 'r%.0s' {1..200})"
echo "== release the root =="; req root-1 "" final "x"
sleep 2
echo "== ROUTER LOG (program lines) =="; grep -E "thunderagent\.(program|route|worker)" "$LOGS/router.log" | sed 's/^.*thunderagent\./thunderagent./' | tail -30
echo "== router errors, if any =="; grep -iE "error|traceback" "$LOGS/router.log" | tail -5
