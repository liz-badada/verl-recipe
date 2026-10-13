"""Metrics over the first dispatch of every (sample, rollout) slot = the trainer's first batch.

The V1 trainer prefetches a second copy of the prompt set while the first is running; session
names carry the sample and rollout indices, so the earliest-started session per slot is the
first-batch one. Wall = first start -> last end of those sessions (or the stop time if unfinished).
"""
import json, re, sys
run = sys.argv[1]
d = json.load(open(f"{run}/summary.json"))
slots = {}
for r in d["sessions"]:
    m = re.match(r"session-sample-(\d+)-rollout-(\d+)-", r["session"])
    if not m or not r.get("start"):
        continue
    key = (int(m.group(1)), int(m.group(2)))
    if key not in slots or r["start"] < slots[key]["start"]:
        slots[key] = r
rows = list(slots.values()); done = [r for r in rows if r.get("done") and r.get("end")]
t0 = min(r["start"] for r in rows); t_end = max(r["end"] for r in done) if done else None
traj = [t for r in done for t in r.get("trajectories", [])]
model = sum(t.get("model_token_count", 0) for t in traj); ctx = sum(t.get("response_len", 0) for t in traj)
wall = (t_end - t0) if t_end else None
out = {"run": run.rstrip("/").split("/")[-1], "slots": len(rows), "done": len(done), "wall_s": wall,
       "model_tok_s": model / wall if wall else None, "ctx_tok_s": ctx / wall if wall else None,
       "latency_mean_s": sum(r["end"] - r["start"] for r in done) / len(done) if done else None,
       "finished": sum(1 for t in traj if t.get("finished")), "reward_mean": sum((t.get("reward_score") or 0) for t in traj) / len(traj) if traj else None}
print(json.dumps(out))
