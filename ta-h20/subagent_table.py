"""subagent_table.py: per-arm subagent metrics for the result pages -> subagent_points.json.

For every run in regime_points.json: sessions that dispatched Claude Code subagents (a
`<function=Agent>` call in the kept trajectory), dispatches, and completion rate / mean duration
of sessions with and without subagents (subagent_split.py).
"""
import glob, json, os, re, subprocess, sys

H = os.path.dirname(os.path.abspath(__file__))
P = json.load(open(f"{H}/regime_points.json"))
out = {}
for regime in ("default", "subagent_prompt"):
    for arm, pts in P[regime].items():
        for d in pts:
            run = d["run"]
            if not os.path.isdir(f"{H}/runs/{run}"):
                continue
            line = subprocess.run([sys.executable, f"{H}/subagent_split.py", f"{H}/runs/{run}"],
                                  capture_output=True, text=True).stdout.strip().splitlines()[-1]
            split = json.loads(line.split(" ", 1)[1])
            w, wo = split["with_subagents"], split["without_subagents"]
            # peak number of programs the native router tracked at once (ThunderAgent telemetry)
            logs = glob.glob(f"{H}/runs/{run}/dynamo/*frontend.log")
            peak = max((int(m) for f in logs for m in re.findall(r"programs=(\d+)", open(f, errors="replace").read())), default=None)
            out[run] = {"regime": regime, "arm": arm, "cc": d["cc"], "tok_s": d["v"],
                        "peak_programs": peak,
                        "sessions": w["sessions"] + wo["sessions"], "with_sub": w["sessions"], "dispatches": w["dispatches"],
                        "finished_rate_with": w["finished_rate"], "finished_rate_without": wo["finished_rate"],
                        "duration_with": w["mean_duration_s"], "duration_without": wo["mean_duration_s"]}
json.dump(out, open(f"{H}/subagent_points.json", "w"), indent=1, ensure_ascii=False)
for run, r in sorted(out.items(), key=lambda kv: (kv[1]["regime"], kv[1]["cc"], kv[1]["arm"])):
    print(f'{r["regime"]:15} cc{r["cc"]:<4} {r["arm"]:10} sessions={r["sessions"]:4} with_sub={r["with_sub"]:4} disp={r["dispatches"]:4} '
          f'peak_programs={r["peak_programs"]} fin_with={r["finished_rate_with"]:.3f} fin_without={r["finished_rate_without"]:.3f} dur={r["duration_with"]}/{r["duration_without"]}')
