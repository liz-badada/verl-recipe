"""subagent_split.py <run>...: session outcomes split by whether the session dispatched subagents.

Joins count_agent_calls.py's per-session Agent-tool counts with summary.json (first BATCH*N sessions
by start time), so the effect of subagent trees on completion, timeouts and duration is visible per arm.
"""
import json, os, sys

def split(run):
    calls = {r["session"]: r for r in json.load(open(f"{run}/agent_calls.json"))["sessions"]}
    scored = json.load(open(f"{run}/summary.json"))["sessions"]
    groups = {"with_subagents": [], "without_subagents": []}
    for s in scored:
        c = calls.get(s["session"])
        if c is None:
            continue
        groups["with_subagents" if c["agent_calls"] else "without_subagents"].append((s, c))
    out = {}
    for name, rows in groups.items():
        n = len(rows)
        fin = sum(1 for s, _ in rows if any(t.get("finished") for t in s.get("trajectories", [])))
        done = sum(1 for s, _ in rows if s.get("done"))
        lat = [s["end"] - s["start"] for s, _ in rows if s.get("end") and s.get("start")]
        out[name] = {"sessions": n, "ended": done, "finished": fin,
                     "finished_rate": round(fin / n, 3) if n else None,
                     "mean_duration_s": round(sum(lat) / len(lat)) if lat else None,
                     "dispatches": sum(c["agent_calls"] for _, c in rows)}
    return out

if __name__ == "__main__":
    for run in sys.argv[1:]:
        print(os.path.basename(run), json.dumps(split(run)))
