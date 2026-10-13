#!/bin/bash
# stop_arm_when_done.sh <run-dir> <container> <expected> <max-wait-s>: stop the arm once the first
# <expected> sessions (by start order) all have trajectories, or after <max-wait-s>.
set +e
export DOCKER_CONFIG=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig
RUN=$1; C=$2; EXPECTED=$3; MAXW=${4:-1200}; t0=$(date +%s)
while :; do
  n=$(ls -dtr "$RUN"/agent_logs/step_1/session-* 2>/dev/null | head -n "$EXPECTED" | while read -r sd; do [ -f "$sd/trajectory.json" ] && echo x; done | wc -l)
  docker ps -q --filter "name=$C" | grep -q . || { echo "container gone"; exit 0; }
  if [ "$n" -ge "$EXPECTED" ] || [ $(( $(date +%s) - t0 )) -ge "$MAXW" ]; then
    sleep 20; echo "ROLLOUT_DONE_EPOCH=$(date +%s) sessions_first${EXPECTED}_done=$n" >> "$RUN/command.txt"
    port=$(grep -o 'starting dynamo.frontend on :[0-9]*' "$RUN/console.log" | head -1 | grep -o '[0-9]*$')
    [ -n "$port" ] && curl -s -m 10 "http://127.0.0.1:$port/metrics" > "$RUN/frontend_metrics.prom" 2>/dev/null
    docker rm -f "$C" >/dev/null 2>&1; echo "stopped $C with $n/$EXPECTED done"; exit 0
  fi
  sleep 15
done
