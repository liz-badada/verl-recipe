DYN_LOG=info,thunderagent=debug
NCCL_P2P_LEVEL=NVL
NCCL_IB_DISABLE=1
VLLM_ALLREDUCE_USE_SYMM_MEM=0
VLLM_ALLREDUCE_USE_FLASHINFER=0
# READY: smc-522ga-0029: GPUs 4-7 have NVLink inactive and P2P over the SYS path hangs; NCCL P2P only over NVLink, TP all-reduce via NCCL (diag 4902210 case 6)
