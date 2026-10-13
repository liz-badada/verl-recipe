#!/bin/bash
#SBATCH -J ta-gw-2gpu
#SBATCH -p l40s@cr+mp/genoa2d24g2l/8gpu-256cpu-2304gb
#SBATCH --gres=gpu:2
#SBATCH --qos=batch-short
#SBATCH --time=03:55:00
#SBATCH --ntasks=1
#SBATCH -w 4u8g-gen-0035
#SBATCH -o /home/scratch.jinyanc_wwfo/ta-validate/gpu-bench/slurm-gw-%j.out
# End-to-end: Claude Code-style trees -> uni-agent Gateway (verl-recipe adapter, real code path)
# -> Dynamo frontend -> 2 vLLM workers. Same blog-regime shape as ta_gpu_sweep.sbatch.
set -uo pipefail
R=/home/scratch.jinyanc_wwfo/ta-validate/gpu-bench; IMG=dynamo-nightly-gpu:20261009; GWIMG=ta-gateway-ci:20261012
MODEL=Qwen/Qwen2.5-7B-Instruct; RES=${RESULTS:-results-gw}
echo "node=$(hostname)"; nvidia-smi --query-gpu=index,name,driver_version,memory.total --format=csv,noheader
docker image inspect $IMG >/dev/null 2>&1 || { echo "IMAGE_MISSING $IMG"; exit 4; }
docker image inspect $GWIMG >/dev/null 2>&1 || { echo "building $GWIMG $(date +%T)"; docker build -q -t $GWIMG -f $R/gw/Dockerfile $R/gw/uni-agent 2>&1 | tail -3; }
docker image inspect $GWIMG >/dev/null 2>&1 || { echo "GW_IMAGE_BUILD_FAILED"; exit 5; }
GPUS="\"device=$(nvidia-smi --query-gpu=uuid --format=csv,noheader | paste -sd,)\""
GW="docker run -d --name tabench-gw --network host --user $(id -u):$(id -g) -v $R/gw/uni-agent:/workspace -v $R/gw/verl-recipe:/workspace/verl/recipe -v $R:/e2e -e PYTHONPATH=/workspace/verl:/workspace -e HF_HOME=/e2e/hf -e HOME=/tmp -w /workspace/verl $GWIMG python /e2e/gw/gateway_server.py --model $MODEL --port 8900 --timeout 900"
for CC in ${CCS:-64 96}; do
  for v in ${VARIANTS:-ta-subagent-tuned kv-router}; do
    echo "=== cc=$CC $v $(date +%T) ==="
    docker ps -aq --filter name=tabench- | xargs -r docker rm -f >/dev/null 2>&1
    OUT=$R/bench/$RES/cc$CC/$v; mkdir -p $OUT
    $GW >/dev/null
    timeout 2700 docker run --rm --name tabench-$v --gpus "$GPUS" --network host --shm-size 8g --user $(id -u):$(id -g) \
      -v $R/src:/src -v $R/src-main:/src-main -v $R:/e2e -e HF_HOME=/e2e/hf -e HOME=/tmp \
      -e MODEL=$MODEL -e GPU_MEM=0.88 -e PER_GPU=1 -e BLOCKS= -e MAX_MODEL_LEN=32768 -e MAX_NUM_SEQS=256 \
      -e RESULTS=$RES/cc$CC -e SESSIONS=$CC -e SUBAGENTS=3 -e TURNS=6 -e ROOT_TURNS=3 -e CONC=$CC -e REQ_TIMEOUT=900 \
      -e ROOT_SYS=8000 -e SUB_SYS=6000 -e TASK=300 -e TOOL=2000 -e MAX_TOKENS=128 -e TOOL_GAP=4 \
      -e GATEWAY_URL=http://127.0.0.1:8900 \
      -e TA_ARGS="${TA_ARGS:---scheduler-interval-seconds 0.5 --resume-hysteresis 0.05}" \
      $IMG bash /e2e/bench/run_variant_gpu.sh $v 2>&1 | grep -E "^\[$v|^docker:|rror"
    docker logs tabench-gw > $OUT/logs/gateway.log 2>&1; docker rm -f tabench-gw >/dev/null 2>&1
    echo "[$v] gateway log: $(grep -ciE 'error|traceback' $OUT/logs/gateway.log) error lines; $(tail -1 $OUT/logs/gateway.log | cut -c1-200)"
  done
done
docker ps -aq --filter name=tabench- | xargs -r docker rm -f >/dev/null 2>&1
echo "ALL GW VARIANTS DONE $(date +%T)"
