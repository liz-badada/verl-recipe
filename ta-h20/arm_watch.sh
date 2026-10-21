#!/bin/bash
# arm_watch.sh <run_name>: block until runs/<run_name>/summary.txt exists, then print the booking numbers and the
# start-validation checks (KV pool per engine, GPU processes per sample, port collisions) plus router counters for TA arms.
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}; r=$H/runs/$1
until [ -f $r/summary.txt ]; do sleep 600; done; sleep 20
date +%T; echo "== $1 done"
python3 $H/engine_rate.py $r | tail -1; python3 $H/engine_rate.py --buckets $r; python3 $H/time_to_512.py $r | tail -1
grep -o '"sessions_done": [0-9]*\|"finished_trajectories": [0-9]*\|"wall_s": [0-9.]*' $r/summary.json | tr '\n' ' '; echo
grep -o "generate_sequences summary: num_input_prompts=[0-9]* num_success_sessions=[0-9]* num_failed_sessions=[0-9]*" $r/console.log | tail -1
grep -rho "GPU KV cache size: [0-9,]* tokens\|max_total_num_tokens=[0-9]*" $r/ | sort | uniq -c
python3 - "$r" <<'PY'
import collections,csv,sys; rows=list(csv.reader(open(f"{sys.argv[1]}/gpu_procs.csv"))); c=collections.Counter(x[0] for x in rows[1:]); print("procs ts",len(c),"max",max(c.values()) if c else 0)
PY
echo "collisions $(grep -c 'Address already in use' $r/console.log)"
f=$r/dynamo/verl_dynamo_replica0_frontend.log
[ -f $f ] && { echo "forced resumes $(grep -c 'forced[a-z ]*resum' $f)"; grep -o "paused_programs=[0-9]*" $f | sort -t= -k2 -n | tail -1; grep -o "programs=[0-9]*" $f | sort -t= -k2 -n | tail -1; }
