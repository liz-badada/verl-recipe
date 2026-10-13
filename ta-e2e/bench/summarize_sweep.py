"""Concurrency sweep table: tok/s, wall, prefix hit, completion per variant and CC."""
import glob, json, re, sys
from pathlib import Path

root = Path(sys.argv[1])
rows = []
for cc_dir in sorted(root.glob("cc*"), key=lambda p: int(p.name[2:])):
    for v in ("ta-subagent", "ta-subagent-tuned", "kv-router", "round-robin"):
        d = cc_dir / v
        if not (d / "load.json").exists():
            continue
        s = json.load(open(d / "load.json"))["summary"]
        def tot(tag, name):
            t = 0.0
            for f in glob.glob(str(d / f"vllm*_{tag}.prom")):
                for line in open(f):
                    if line.startswith(f"vllm:{name}"):
                        t += float(line.rsplit(" ", 1)[1])
            return t
        q = tot("after", "prefix_cache_queries_total") - tot("before", "prefix_cache_queries_total")
        h = tot("after", "prefix_cache_hits_total") - tot("before", "prefix_cache_hits_total")
        row = {"cc": int(cc_dir.name[2:]), "variant": v, "done": f'{s["completed_sessions"]}/{s["sessions"]}', "errors": s["errors"],
               "wall_s": round(s["wall_s"], 1), "tok_per_s": round(s["completion_tokens_per_s"], 1),
               "sess_p50_s": round(sorted(x["latency_s"] for x in json.load(open(d / "load.json"))["sessions"])[s["sessions"] // 2], 1) if s["sessions"] else None,
               "prefix_hit": round(h / q, 3) if q else None}
        ra = d / "router_after.json"
        if ra.exists() and ra.stat().st_size:
            c = json.load(open(ra))["counters"]
            row.update(pauses=c["program_pauses_total"], forced=c["forced_resumes_total"], leaked=c["programs_created_total"] - c["programs_ended_total"])
        rows.append(row)
cols = ["cc", "variant", "done", "errors", "wall_s", "tok_per_s", "sess_p50_s", "prefix_hit", "pauses", "forced", "leaked"]
print("| " + " | ".join(cols) + " |"); print("|" + "---|" * len(cols))
for r in rows:
    print("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
json.dump(rows, open(root / "sweep.json", "w"), indent=1)
