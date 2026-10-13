"""Trainer-faithful metric: how long until 512 trajectories had been collected, from any sessions.

This is what one rollout step costs the trainer (train_batch_size 32 x n 16). Tokens are summed
over those first 512 completed sessions; wall runs from the first session start.
"""
import json, sys
for run in sys.argv[1:]:
    d = json.load(open(f"{run}/summary.json"))
    rows = [r for r in d.get("sessions_all", d["sessions"]) if r.get("start")]
    t0 = min(r["start"] for r in rows)
    done = sorted((r for r in rows if r.get("done") and r.get("end")), key=lambda r: r["end"])
    first = done[:512]
    if len(first) < 512:
        print(f"{run.split('/')[-1]:36s} only {len(first)} trajectories collected (stopped at wall {d['summary']['wall_s']:.0f}s)"); continue
    wall = first[-1]["end"] - t0
    traj = [t for r in first for t in r.get("trajectories", [])]
    model = sum(t.get("model_token_count", 0) for t in traj); ctx = sum(t.get("response_len", 0) for t in traj)
    fin = sum(1 for t in traj if t.get("finished")); rew = sum((t.get("reward_score") or 0) for t in traj) / len(traj)
    print(f"{run.split('/')[-1]:36s} 512 trajectories in {wall:6.0f}s  model {model/wall:6.1f} tok/s  ctx {ctx/wall:7.1f} tok/s  finished {fin}  reward {rew:.3f}  latency {sum(r['end']-r['start'] for r in first)/512:.0f}s")
