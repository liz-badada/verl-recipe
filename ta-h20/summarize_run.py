"""Summarize one rollout-only arm from its Uni-Agent agent logs.

Per session the framework writes task.log (timestamped) and trajectory.json (one entry per
materialized trajectory: turns, prompt/response lengths, model tokens, reward). Wall time is
measured from the first session start to the last session end, so it is the same quantity
for every arm regardless of router. Subagent trajectories are the extra chains a session
materialized beyond its main one.
"""
import json
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path

TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


def span(path):
    first = last = None
    try:
        with open(path, errors="replace") as fp:
            for line in fp:
                m = TS.match(line)
                if m:
                    t = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
                    first = t if first is None else first
                    last = t
    except OSError:
        pass
    return first, last


def main(run):
    run = Path(run)
    sessions = sorted((run / "agent_logs").glob("step_*/session-*"))
    rows = []
    for s in sessions:
        meta = {}
        if (s / "trajectory.json").exists():
            meta = json.loads((s / "trajectory.json").read_text())
        start, end = span(s / "task.log")
        fstart, fend = span(s / "framework.log")
        start = min(t for t in (start, fstart) if t) if (start or fstart) else None
        end = max(t for t in (end, fend) if t) if (end or fend) else None
        rows.append({"session": s.name, "start": start, "end": end, "done": bool(meta), **meta})
    # The V1 trainer keeps prefetching prompt groups after the first batch, so more sessions than
    # BATCH*N exist by the time the run is stopped. Score the first BATCH*N sessions by start time;
    # the same rule applies to every arm.
    expected = None
    cmd = run / "command.txt"
    if cmd.exists():
        m = re.search(r"BATCH=(\d+) N=(\d+)", cmd.read_text())
        if m:
            expected = int(m.group(1)) * int(m.group(2))
    rows.sort(key=lambda r: (r["start"] is None, r["start"] or 0))
    all_rows = list(rows)
    if expected and len(rows) > expected:
        rows = rows[:expected]
    done = [r for r in rows if r["done"]]
    trajs = [t for r in done for t in r.get("trajectories", [])]
    starts = [r["start"] for r in rows if r["start"]]
    ends = [r["end"] for r in done if r["end"]]
    wall = (max(ends) - min(starts)) if starts and ends else None
    model_tokens = sum(t.get("model_token_count", 0) for t in trajs)
    context_tokens = sum(t.get("response_len", 0) for t in trajs)
    turns = [t.get("num_turns", 0) for t in trajs]
    # Effective concurrency: how many scored sessions were alive at once (sandbox slots cap it below CONCURRENCY).
    events = sorted([(r["start"], 1) for r in rows if r["start"]] + [(r["end"], -1) for r in done if r["end"]])
    cur = peak = 0
    for _, delta in events:
        cur += delta
        peak = max(peak, cur)
    summary = {
        "run": run.name,
        "peak_concurrent_sessions": peak,
        "sessions_scored": len(rows), "sessions_done": len(done), "expected": expected,
        "trajectories": len(trajs),
        "subagent_trajectories": sum(max(0, r.get("num_trajectories", 1) - 1) for r in done),
        "sessions_with_subagents": sum(1 for r in done if r.get("num_trajectories", 1) > 1),
        "wall_s": wall,
        "model_tokens": model_tokens, "context_tokens": context_tokens,
        "model_tokens_per_s": model_tokens / wall if wall else None,
        "context_tokens_per_s": context_tokens / wall if wall else None,
        "turns_mean": statistics.mean(turns) if turns else None,
        "response_len_mean": statistics.mean([t.get("response_len", 0) for t in trajs]) if trajs else None,
        "finished_trajectories": sum(1 for t in trajs if t.get("finished")),
        "reward_mean": statistics.mean([t.get("reward_score") or 0 for t in trajs]) if trajs else None,
        "session_latency_mean_s": statistics.mean([r["end"] - r["start"] for r in done if r["start"] and r["end"]]) if done else None,
    }
    cmd = run / "command.txt"
    if cmd.exists():
        for line in cmd.read_text().splitlines():
            if line.startswith("ROLLOUT_DONE_EPOCH") or line.startswith("ARM="):
                summary.setdefault("notes", []).append(line[:200])
    (run / "summary.json").write_text(json.dumps({"summary": summary, "sessions": rows, "sessions_all": all_rows}, indent=1, default=str))
    print(json.dumps(summary, indent=1, default=str))


if __name__ == "__main__":
    main(sys.argv[1])
