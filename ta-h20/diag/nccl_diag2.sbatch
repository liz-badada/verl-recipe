#!/bin/bash
#SBATCH -J nccl-diag2
#SBATCH -p h200-nvl@qs1/x14dbgap/8gpu-288cpu-2304gb
#SBATCH --gres=gpu:8
#SBATCH --qos=batch-short
#SBATCH --time=00:50:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=0
#SBATCH -o /home/scratch.jinyanc_wwfo/ta-h20/slurm-nccl2-%j.out
SC=/home/scratch.jinyanc_wwfo/ta-h20; IMG=verl-recipe-thunderagent:rust-ta-uniagent-20261012
echo "node=$(hostname)"; ip -o -4 addr show | awk '{print $2, $4}' | grep -v -E '^lo|docker|br-' | head -4
n=0
run() { n=$((n+1)); echo "=== [$n] $*"; docker rm -f nccltest >/dev/null 2>&1; timeout 200 docker run --rm --name nccltest --gpus all --network host --ipc=host --shm-size 64g --user $(id -u):$(id -g) -e HOME=/tmp -e USER=$(id -un) -e LOGNAME=$(id -un) "$@" -v $SC/ci/diag:/diag:ro $IMG torchrun --nproc_per_node 8 --master_port $((29600+n)) /diag/nccl_test.py 2>&1 | grep -E '^OK|Timeout|NCCL INFO (NET|Using|Channel|Connected|Setting)|NCCL WARN|misc/socket|Error' | sort | uniq -c | sort -rn | head -8; docker rm -f nccltest >/dev/null 2>&1; }
run -e NCCL_DEBUG=INFO -e NCCL_DEBUG_SUBSYS=INIT,NET
run -e NCCL_IB_DISABLE=1
run -e NCCL_P2P_DISABLE=1
run -e NCCL_IB_DISABLE=1 -e NCCL_P2P_DISABLE=1
run -e NCCL_NET_GDR_LEVEL=0
run -e NCCL_P2P_LEVEL=NVL -e NCCL_IB_DISABLE=1
run -e NCCL_IB_DISABLE=1 -e NCCL_SHM_DISABLE=1
echo DIAG2_DONE
