"""CPU-side check: resolve a dataset row with the task YAML, build the SWE task and start its
docker sandbox the way the framework does, then confirm Claude Code resolves inside it."""
import asyncio, inspect, json
import pyarrow.parquet as pq
from uni_agent.tasks import TaskConfigResolver, get_task

row = pq.read_table("/h20/data/swe_bench_verified_32_task.parquet").slice(0, 1).to_pylist()[0]
sample = dict(row["extra_info"]["tools_kwargs"]["task"]); sample["prompt"] = row["prompt"]
task = TaskConfigResolver.from_file("/h20/task_config_claude_code_docker.yaml").resolve(
    sample, runtime_model={"base_url": "http://10.6.131.6:9/sessions/x/v1", "api_key": "EMPTY", "model_name": "Qwen3-Coder-30B-A3B-Instruct"})
print("resolved sandbox:", json.dumps(task["sandbox"], default=str)[:400])
print("resolved agent:", json.dumps(task["agent"], default=str)[:400])
print("prompt[0][:120]:", str(task["prompt"][0])[:160])
obj = get_task(task)
t = obj if hasattr(obj, "run") else obj(task)
print("task object:", type(t).__name__)

async def main():
    async with t.build_sandbox() as sb:
        r = await sb.exec_shell("command -v claude; claude --version; whoami; git -C /testbed rev-parse --short HEAD; nproc")
        print("sandbox stdout:", r.stdout.strip().replace("\n", " | "), "| stderr:", r.stderr.strip()[:200])
asyncio.run(main())
