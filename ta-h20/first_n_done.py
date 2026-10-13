"""Print how many of the first N sessions (by start time in their logs) have a trajectory."""
import glob, re, sys
from datetime import datetime
run, n = sys.argv[1], int(sys.argv[2])
ts = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
rows = []
for s in glob.glob(f"{run}/agent_logs/step_1/session-*"):
    start = None
    for name in ("framework.log", "task.log"):
        try:
            with open(f"{s}/{name}", errors="replace") as fp:
                for line in fp:
                    m = ts.match(line)
                    if m:
                        t = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
                        start = t if start is None else min(start, t)
                        break
        except OSError:
            pass
    rows.append((start if start is not None else float("inf"), s))
rows.sort()
first = rows[:n]
print(sum(1 for _, s in first if glob.glob(f"{s}/trajectory.json")), len(first))
