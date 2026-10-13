"""Convert the phase-1 SWE-bench Verified 32-instance parquet into Uni-Agent's Task Config format.

Mirrors uni_agent.tasks.swe_bench.preprocess: an agent-neutral user prompt holding the
problem statement, and extra_info.tools_kwargs.task carrying the serialized Task Config
(name, canonical swebench image, evaluator metadata). The task YAML adds agent/sandbox.
"""
import ast
import sys

import pyarrow as pa
import pyarrow.parquet as pq

FIELDS = ["instance_id", "repo", "version", "base_commit", "patch", "test_patch", "problem_statement", "FAIL_TO_PASS", "PASS_TO_PASS"]


def image_name(instance_id):
    return f"swebench/sweb.eval.x86_64.{instance_id.lower().replace('__', '_1776_')}"


def main(src, dst):
    rows = []
    for row in pq.read_table(src).to_pylist():
        extra = row["extra_info"]
        extra = ast.literal_eval(extra) if isinstance(extra, str) else extra
        meta = extra["tools_kwargs"]["reward"]["metadata"]
        metadata = {k: (str(meta[k]) if k == "version" else meta[k]) for k in FIELDS}
        task = {"name": "swe_bench", "sandbox": {"image": image_name(meta["instance_id"])}, "metadata": metadata}
        rows.append({
            "data_source": "princeton-nlp/SWE-bench_Verified",
            "prompt": [{"role": "user", "content": meta["problem_statement"]}],
            "extra_info": {"tools_kwargs": {"task": task}, "index": len(rows)},
        })
    pq.write_table(pa.Table.from_pylist(rows), dst)
    print(len(rows), "rows ->", dst, "e.g.", rows[0]["extra_info"]["tools_kwargs"]["task"]["sandbox"])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
