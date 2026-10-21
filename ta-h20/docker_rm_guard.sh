#!/bin/bash
# Re-issue docker rm -f for an arm whose container is already exited but stuck in "Removal In Progress"
# (seen 2026-10-21 on global-h20v29cc512: the rollout finished at 14:45, dockerd held the removal for
# 2 h 24 min and the docker run --rm client never returned, so sweep_cc.sh could not start the next arm).
# Only containers whose run dir carries ROLLOUT_DONE_EPOCH older than 180 s are touched.
H=${H:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}
while sleep 120; do
  docker ps -a --format '{{.Names}} {{.Status}}' 2>/dev/null | awk '$2=="Removal"{print $1}' | while read -r name; do
    f=$H/runs/$name/command.txt; [ -f "$f" ] || continue
    done_at=$(grep -o 'ROLLOUT_DONE_EPOCH=[0-9]*' "$f" | tail -1 | cut -d= -f2); [ -n "$done_at" ] || continue
    [ $(( $(date +%s) - done_at )) -ge 180 ] || continue
    echo "[$(date +%T)] $name stuck in Removal In Progress since $(date -d @$done_at +%T); docker rm -f again"
    timeout 60 docker rm -f "$name" >/dev/null 2>&1 && echo "[$(date +%T)] $name removed"
  done
done
