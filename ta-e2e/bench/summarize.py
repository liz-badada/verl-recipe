"""Table of the four variants + scorer-shaped before/after JSON for the TA variants."""
import json, statistics, sys
from pathlib import Path

root = Path(sys.argv[1])
out = Path(sys.argv[2]) if len(sys.argv) > 2 else root
out.mkdir(parents=True, exist_ok=True)
rows = []
for v in ("ta-subagent", "ta-subagent-tuned", "ta-main", "kv-router", "round-robin"):
    d = root / v
    if not (d / "load.json").exists():
        continue
    load = json.load(open(d / "load.json"))
    fb, fa = json.load(open(d / "frontend_before.json")), json.load(open(d / "frontend_after.json"))
    cached = fa["dynamo_frontend_cached_tokens_sum"] - fb["dynamo_frontend_cached_tokens_sum"]
    inp = fa["dynamo_frontend_input_sequence_tokens_sum"] - fb["dynamo_frontend_input_sequence_tokens_sum"]
    sess = sorted(s["latency_s"] for s in load["sessions"])
    turns = [t["latency_s"] for t in load["turns"] if not t["final"]]
    row = {
        "variant": v, "requests": load["summary"]["requests"], "errors": load["summary"]["errors"],
        "completed_sessions": load["summary"].get("completed_sessions"),
        "wall_s": round(load["summary"]["wall_s"], 1), "tok_per_s": round(load["summary"].get("completion_tokens_per_s", 0), 1),
        "session_p50_s": round(statistics.median(sess), 2), "session_p95_s": round(sess[int(0.95 * (len(sess) - 1))], 2),
        "turn_mean_s": round(statistics.mean(turns), 3),
        "input_tokens": int(inp), "cached_tokens": int(cached), "kv_hit_rate": round(cached / inp, 3) if inp else None,
    }
    ra = d / "router_after.json"
    if ra.exists() and ra.stat().st_size:
        c = json.load(open(ra))["counters"]
        row.update(programs_created=c["programs_created_total"], programs_ended=c["programs_ended_total"],
                   leaked=c["programs_created_total"] - c["programs_ended_total"],
                   pauses=c["program_pauses_total"], forced_resumes=c["forced_resumes_total"], unpinned=c["unpinned_turns_total"])
        # Scorer-shaped captures: vLLM counts prefix-cache queries/hits in tokens.
        for tag, fm, rm in (("before", fb, d / "router_before.json"), ("after", fa, ra)):
            counters = json.load(open(rm))["counters"] if rm.exists() and rm.stat().st_size else {}
            json.dump({"counters": counters, "vllm": {"prefix_cache_queries_total": fm["dynamo_frontend_input_sequence_tokens_sum"],
                                                       "prefix_cache_hits_total": fm["dynamo_frontend_cached_tokens_sum"]}},
                      open(out / f"{v}_scorer_{tag}.json", "w"))
    rows.append(row)
cols = sorted({k for r in rows for k in r}, key=lambda k: ["variant", "requests", "errors", "completed_sessions", "wall_s", "tok_per_s", "session_p50_s", "session_p95_s", "turn_mean_s", "input_tokens", "cached_tokens", "kv_hit_rate", "programs_created", "programs_ended", "leaked", "pauses", "forced_resumes", "unpinned"].index(k))
print("| " + " | ".join(cols) + " |"); print("|" + "---|" * len(cols))
for r in rows:
    print("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
json.dump(rows, open(out / "summary.json", "w"), indent=1)
