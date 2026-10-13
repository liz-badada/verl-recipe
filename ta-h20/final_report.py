"""Aggregate one benchmark sweep: per-arm first-512 summary, common-wall comparison, Claude Code
exit outcomes, subagent dispatches, ThunderAgent forced resumes and vLLM scheduler stats."""
import glob, json, re, statistics, sys
H = "/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20"
sys.path.insert(0, H)

def vllm_stats(paths):
    rx = re.compile(r"generation throughput: ([0-9.]+) tokens/s, Running: (\d+) reqs, Waiting: (\d+) reqs, GPU KV cache usage: ([0-9.]+)%, Prefix cache hit rate: ([0-9.]+)%")
    gen, kv, hit, run = [], [], [], []
    for p in paths:
        for line in open(p, errors="replace"):
            m = rx.search(line)
            if m:
                gen.append(float(m.group(1))); run.append(int(m.group(2))); kv.append(float(m.group(4))); hit.append(float(m.group(5)))
    if not gen:
        return None
    return {"samples": len(gen), "gen_tok_s_mean_per_engine": statistics.mean(gen), "kv_usage_mean_pct": statistics.mean(kv),
            "prefix_hit_mean_pct": statistics.mean(hit), "running_reqs_mean": statistics.mean(run)}

def arm(run):
    s = json.load(open(f"{run}/summary.json"))["summary"]
    logs = glob.glob(f"{run}/agent_logs/step_1/*/task.log")
    outcome = {"finished_ok": 0, "exit1_max_turns": 0, "timed_out": 0}
    for p in logs:
        t = open(p, errors="replace").read()
        if "timed out after" in t: outcome["timed_out"] += 1
        elif "claude finished (exit 0)" in t: outcome["finished_ok"] += 1
        elif "claude exited 1" in t: outcome["exit1_max_turns"] += 1
    calls = json.load(open(f"{run}/agent_calls.json"))["summary"] if glob.glob(f"{run}/agent_calls.json") else None
    fe = glob.glob(f"{run}/dynamo/*frontend.log")
    forced = sum(open(fe[0], errors="replace").read().count("forced_resumes=") if fe else 0 for _ in [0])
    stats = vllm_stats(glob.glob(f"{run}/dynamo/*/replica*_shard0.log") or [f"{run}/console.log"])
    return {"run": run.split("/")[-1], "summary": s, "claude_outcomes": outcome, "subagents": calls, "ta_forced_resumes": forced, "vllm": stats}

runs = sys.argv[1:]
report = [arm(r) for r in runs]
json.dump(report, open(f"{H}/runs/final_report_{runs[0].split('/')[-1].split('-')[-1]}.json", "w"), indent=1, default=str)
for a in report:
    s = a["summary"]; o = a["claude_outcomes"]; c = a["subagents"] or {}; v = a["vllm"] or {}
    print(f"{a['run']}: done {s['sessions_done']}/{s['expected']} wall {s['wall_s']:.0f}s model {s['model_tokens_per_s']:.1f} tok/s ctx {s['context_tokens_per_s']:.1f} tok/s "
          f"latency {s['session_latency_mean_s']:.0f}s | claude ok {o['finished_ok']} max-turns {o['exit1_max_turns']} timeout {o['timed_out']} | "
          f"subagent dispatches {c.get('subagent_dispatches')} in {c.get('sessions_dispatching_subagents')}/{c.get('sessions')} | TA forced resumes {a['ta_forced_resumes']} | "
          f"vLLM gen/engine {v.get('gen_tok_s_mean_per_engine', 0):.0f} tok/s KV {v.get('kv_usage_mean_pct', 0):.0f}% prefix-hit {v.get('prefix_hit_mean_pct', 0):.0f}%")
