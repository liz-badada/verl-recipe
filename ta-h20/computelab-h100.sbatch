#!/bin/bash
#SBATCH -J ta-uniagent-h100
#SBATCH -p h100-80gb-hbm3@cr+mp/viking@cr+mp/8gpu-224cpu-2048gb
#SBATCH --gres=gpu:8
#SBATCH --qos=batch
#SBATCH --time=24:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=160
#SBATCH -o /home/scratch.jinyanc_wwfo/ta-h20/slurm-h100-%j.out
# Hardware-selection companion to the 8xH20 benchmark: same image, data, model, prompt and arms on 8x H100 80 GB.
# H100 has 80 GB, so the per-GPU KV cap is 48 GiB instead of 60 GiB (weights ~15 GB/GPU at TP4); both arms share it.
# Concurrency points: 256, 128, then 512 last (512 concurrent sandboxes once took a computelab docker daemon down).
set -uo pipefail
SC=/home/scratch.jinyanc_wwfo/ta-h20; export TA_H20_ROOT=$SC/ci HF_HOME=$SC/hf
echo "node=$(hostname) start=$(date) uid=$(id -u)"; nvidia-smi --query-gpu=index,name,driver_version,memory.total --format=csv,noheader; nvidia-smi topo -m | head -12; df -h /raid /var/lib/docker 2>/dev/null | tail -2
for i in $(seq 1 40); do timeout 30 docker version --format 'docker {{.Server.Version}}' 2>/dev/null && break; echo "docker daemon not answering yet ($i)"; sleep 15; done
timeout 30 docker version >/dev/null 2>&1 || { echo NO_DOCKER; exit 2; }
[ -f $SC/model/Qwen3-Coder-30B-A3B-Instruct/config.json ] || { echo NO_MODEL; exit 2; }
cat $SC/images.txt | xargs -P 8 -I{} sh -c 'docker image inspect {} >/dev/null 2>&1 || docker pull -q {} >/dev/null 2>&1 || echo "PULL_FAILED {}"'
echo "sandbox images present: $(cat $SC/images.txt | xargs -I{} sh -c 'docker image inspect {} >/dev/null 2>&1 && echo ok' | wc -l)/32 $(date +%T)"
IMG=verl-recipe-thunderagent:rust-ta-uniagent-20261012
docker image inspect $IMG >/dev/null 2>&1 || cat $SC/image.tar.zst.part-* | zstd -d -T8 | docker load | tail -1
docker image inspect $IMG >/dev/null 2>&1 || { echo IMAGE_LOAD_FAILED; exit 4; }
echo "image ready $(date +%T)"
printf '%s\n' "DYN_LOG=info,thunderagent=debug" "VLLM_ALLREDUCE_USE_SYMM_MEM=0" "VLLM_ALLREDUCE_USE_FLASHINFER=0" > $SC/ci/env.sh
export UNIAGENT=$SC/uni-agent RECIPE=$SC/verl-recipe MODEL_DIR=$SC/model/Qwen3-Coder-30B-A3B-Instruct IMAGE=$IMG TASK_CONFIG=/h20/task_config_claude_code_docker.computelab.yaml
export KV_BYTES=${KV_BYTES:-51539607552} GPU_MEM=${GPU_MEM:-0.92} TP=${TP:-4} SITE=h100 ARMS="${ARMS:-ta-native global}" CCS="${CCS:-256 128 512}"
TAG=$(date +%m%d%H%M)
# Gate: the gateway close fix (recipe 9f32e49) must release every program before any arm is measured.
TASK_CONFIG=/h20/task_config_claude_code_docker.computelab.leaksmoke.yaml bash $SC/ci/leak_smoke.sh $TAG | tee $SC/ci/runs/leak_smoke-h100-$TAG.log | grep -q LEAK_SMOKE_PASS || { echo SMOKE_FAILED; exit 5; }
sleep 90
bash $SC/ci/sweep_cc.sh $TAG
echo "end=$(date)"
