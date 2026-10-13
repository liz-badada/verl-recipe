"""Count Claude Code subagent dispatches per session from the materialized response tokens.

The gateway keeps one trajectory per session (trajectory_selection=longest), so the number of
subagent chains is not visible in trajectory.json. The dispatcher's own responses are: every
`<function=Agent>` tool call in the kept trajectory is one subagent dispatched.
"""
import glob, json, re, sys
import numpy as np
from transformers import AutoTokenizer

run, model = sys.argv[1], sys.argv[2]
tok = AutoTokenizer.from_pretrained(model)
rows = []
for npz in sorted(glob.glob(f"{run}/agent_logs/step_1/*/trajectory.npz")):
    z = np.load(npz)
    keys = [k for k in z.files if k.endswith("_response_ids")]
    text = " ".join(tok.decode(z[k].tolist()) for k in keys)
    rows.append({"session": npz.split("/")[-2], "agent_calls": len(re.findall(r"<function=Agent>", text)),
                 "tool_calls": len(re.findall(r"<function=", text)), "trajectories": len(keys)})
n = len(rows); with_sub = sum(1 for r in rows if r["agent_calls"]); calls = sum(r["agent_calls"] for r in rows)
out = {"sessions": n, "sessions_dispatching_subagents": with_sub, "subagent_dispatches": calls,
       "dispatches_per_dispatching_session": calls / with_sub if with_sub else 0,
       "tool_calls_total": sum(r["tool_calls"] for r in rows)}
json.dump({"summary": out, "sessions": rows}, open(f"{run}/agent_calls.json", "w"), indent=1)
print(json.dumps(out))
