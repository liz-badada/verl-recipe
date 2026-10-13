#!/bin/bash
#SBATCH -J nccl-diag
#SBATCH -p h200-nvl@qs1/x14dbgap/8gpu-288cpu-2304gb
#SBATCH --gres=gpu:8
#SBATCH --qos=batch-short
#SBATCH --time=00:40:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=0
#SBATCH -o /home/scratch.jinyanc_wwfo/ta-h20/slurm-nccl-%j.out
SC=/home/scratch.jinyanc_wwfo/ta-h20; IMG=verl-recipe-thunderagent:rust-ta-uniagent-20261012
echo "node=$(hostname)"; nvidia-smi topo -m | head -12; ls /dev/infiniband 2>/dev/null | head -3; ibstat 2>/dev/null | grep -E 'CA|State' | head -6
run() { echo "=== $*"; timeout 300 docker run --rm --gpus all --network host --ipc=host --shm-size 64g --user $(id -u):$(id -g) -e HOME=/tmp -e USER=$(id -un) -e LOGNAME=$(id -un) "$@" -v $SC/ci/diag:/diag:ro $IMG torchrun --nproc_per_node 8 --master_port 29517 /diag/nccl_test.py 2>&1 | grep -E 'OK|Error|error|Timeout|NCCL WARN' | head -5; }
run -e NCCL_DEBUG=WARN
run -e NCCL_IB_DISABLE=1
run -e NCCL_P2P_DISABLE=1
run -e NCCL_IB_DISABLE=1 -e NCCL_P2P_DISABLE=1
run -e NCCL_IB_DISABLE=1 -e NCCL_SHM_DISABLE=1
echo DIAG_DONE
