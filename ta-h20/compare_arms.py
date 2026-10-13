"""Compare arms at a common rollout wall budget.

Each arm's summary.json holds per-session rows (start, end, trajectories). For a budget W, a
session counts if it finished within W seconds of the arm's first session start; tokens are
summed over those sessions. This removes the dependence on when each arm happened to be stopped.
Usage: compare_arms.py <wall_s|auto> <run-dir>...   (auto = the smallest arm stop wall)
"""
import json, sys

def load(run):
    d = json.load(open(f"{run}/summary.json"))
    rows = [r for r in d["sessions"] if r.get("start")]
    t0 = min(r["start"] for r in rows)
    return d["summary"], rows, t0

def at(rows, t0, w):
    done = [r for r in rows if r.get("done") and r.get("end") and r["end"] - t0 <= w]
    traj = [t for r in done for t in r.get("trajectories", [])]
    model = sum(t.get("model_token_count", 0) for t in traj); ctx = sum(t.get("response_len", 0) for t in traj)
    lat = [r["end"] - r["start"] for r in done]
    return {"done": len(done), "model_tok_s": model / w, "ctx_tok_s": ctx / w,
            "latency_mean_s": sum(lat) / len(lat) if lat else None,
            "reward_mean": sum((t.get("reward_score") or 0) for t in traj) / len(traj) if traj else None}

arms = {run.rstrip("/").split("/")[-1]: load(run) for run in sys.argv[2:]}
w = sys.argv[1]
w = min(s["wall_s"] for s, _, _ in arms.values()) if w == "auto" else float(w)
print(f"common wall budget {w:.0f} s")
for name, (s, rows, t0) in arms.items():
    m = at(rows, t0, w)
    print(f"{name:40s} done={m['done']:3d}/{s['expected']} model={m['model_tok_s']:6.1f} tok/s ctx={m['ctx_tok_s']:7.1f} tok/s "
          f"latency={m['latency_mean_s'] or 0:6.0f}s reward={m['reward_mean'] or 0:.3f} (own stop: {s['sessions_done']} @ {s['wall_s']:.0f}s)")
