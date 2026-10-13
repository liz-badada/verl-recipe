"""8-GPU NCCL sanity: broadcast from rank 0 and all-reduce, timed, with the env the trainer uses."""
import os, time, torch, torch.distributed as dist
dist.init_process_group("nccl", timeout=__import__("datetime").timedelta(seconds=120))
r = dist.get_rank(); torch.cuda.set_device(r)
x = torch.ones(64 << 20, dtype=torch.bfloat16, device="cuda") * (r + 1)  # 128 MB
t0 = time.time(); dist.broadcast(x, src=0); torch.cuda.synchronize(); t1 = time.time()
dist.all_reduce(x); torch.cuda.synchronize(); t2 = time.time()
cpu = torch.randn(32 << 20, dtype=torch.bfloat16)
t3 = time.time(); g = cpu.to("cuda"); dist.broadcast(g, src=0); torch.cuda.synchronize(); t4 = time.time()
if r == 0:
    print(f"OK broadcast {t1-t0:.2f}s allreduce {t2-t1:.2f}s cpu->gpu+broadcast {t4-t3:.2f}s value {x[0].item()} env NCCL_IB_DISABLE={os.environ.get('NCCL_IB_DISABLE')} NCCL_P2P_DISABLE={os.environ.get('NCCL_P2P_DISABLE')}", flush=True)
dist.destroy_process_group()
