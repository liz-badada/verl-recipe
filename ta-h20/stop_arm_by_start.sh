#!/bin/bash
# stop_arm_by_start.sh <run-dir> <container> <expected> <arm-start-epoch> <max-s>
set +e; export DOCKER_CONFIG=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/dockerconfig
H=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20; RUN=$1; C=$2; EXPECTED=$3; T0=$4; MAXS=$5
while :; do
  n=$(python3 $H/first_n_done.py "$RUN" "$EXPECTED" 2>/dev/null | awk '{print $1+0}')
  docker ps -q --filter "name=$C" | grep -q . || { echo "container gone"; exit 0; }
  if [ "$n" -ge "$EXPECTED" ] || [ $(( $(date +%s) - T0 )) -ge "$MAXS" ]; then
    sleep 20; echo "ROLLOUT_DONE_EPOCH=$(date +%s) sessions_first${EXPECTED}_done=$n" >> "$RUN/command.txt"
    port=$(grep -o 'starting dynamo.frontend on :[0-9]*' "$RUN/console.log" | head -1 | grep -o '[0-9]*$'); [ -n "$port" ] && curl -s -m 10 "http://127.0.0.1:$port/metrics" > "$RUN/frontend_metrics.prom" 2>/dev/null
    docker rm -f "$C" >/dev/null 2>&1; echo "stopped $C with $n/$EXPECTED done after $(( $(date +%s) - T0 )) s"; exit 0
  fi
  sleep 30
done
