#!/bin/bash
# smoke_then_rerun.sh [tag]: validate the gateway close fix with leak_smoke.sh, then re-measure the TA arms.
# The rerun only starts on a passing smoke, so a still-leaking build cannot produce benchmark data.
set -uo pipefail
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; TAG=${1:-$(date +%m%d%H%M)}
bash $H/leak_smoke.sh $TAG | tee $H/runs/leak_smoke-$TAG.log | grep -q LEAK_SMOKE_PASS || { echo "[$(date +%T)] smoke failed; rerun not started"; exit 1; }
sleep 90
exec bash $H/rerun_ta.sh $TAG
