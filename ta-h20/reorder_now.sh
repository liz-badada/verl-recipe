#!/bin/bash
# reorder_now.sh: stop rerun_ta.sh / sweep_cc.sh (global 512 would start next) and the two waiting chains,
# leave the running global 384 run_arm.sh alone, then launch after_384.sh (CC 64 / 128 first).
H=/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20
kill 1729142 1292092 1398323 1398326 2973552 2>/dev/null; sleep 2
echo "schedulers left: $(ps -o pid= -p 1729142 1292092 1398323 1398326 2973552 2>/dev/null | wc -l) (want 0)"
echo "global 384 run_arm alive: $(ps -o pid= -p 3729911 | wc -l) (want 1)"; docker ps --format '{{.Names}} {{.Status}}' | head -3
cd $H && nohup bash $H/after_384.sh 10141340 10150700 > $H/runs/after_384-10150700.log 2>&1 &
sleep 1; pgrep -af after_384.sh | grep -v pgrep
