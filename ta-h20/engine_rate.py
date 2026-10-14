"""engine_rate.py <run>...: engine-side throughput from the vLLM scheduler stats each engine logs every ~10 s.

Counts every generated token (sessions that later timed out or were still running at the stop included),
so it is independent of how many sessions finished. Window = first to last stats line with Running > 0.
"""
import glob, os, re, sys
from datetime import datetime

PAT = re.compile(r"Avg prompt throughput: ([\d.]+) tokens/s, Avg generation throughput: ([\d.]+) tokens/s, "
                 r"Running: (\d+) reqs, Waiting: (\d+) reqs, GPU KV cache usage: ([\d.]+)%, Prefix cache hit rate: ([\d.]+)%")
G_TS = re.compile(r"\(vLLMHttpServer pid=(\d+)\).*?INFO (\d\d)-(\d\d) (\d\d):(\d\d):(\d\d)")
T_TS = re.compile(r"^\S*?(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)")

def samples(run):
    out = {}  # engine -> [(t, prompt, gen, running, kv, hit)]
    files = glob.glob(f"{run}/dynamo/*/replica*_shard0.log")
    if files:
        for f in files:
            eng = os.path.basename(f).split("_")[0]
            for line in open(f, errors="replace"):
                m = PAT.search(line); ts = T_TS.match(line)
                if m and ts:
                    y, mo, d, hh, mm, ss = map(int, ts.groups())
                    out.setdefault(eng, []).append((datetime(y, mo, d, hh, mm, ss).timestamp(), *map(float, m.groups())))
    else:
        for line in open(f"{run}/console.log", errors="replace"):
            m = PAT.search(line); ts = G_TS.search(line)
            if m and ts:
                pid, mo, d, hh, mm, ss = ts.groups()
                out.setdefault(pid, []).append((datetime(2026, int(mo), int(d), int(hh), int(mm), int(ss)).timestamp(), *map(float, m.groups())))
    return out

def buckets(run, width=600):
    """Per-bucket generation tok/s (both engines) along the active window, to see ramp-up and tail."""
    eng = samples(run); t0 = min(x[0] for s in eng.values() for x in s if x[3] > 0)
    acc = {}
    for s in eng.values():
        s.sort()
        for i in range(1, len(s)):
            b = int((s[i][0] - t0) // width); dt = min(s[i][0] - s[i-1][0], 30)
            a = acc.setdefault(b, [0.0, 0.0]); a[0] += s[i][2] * dt; a[1] += s[i][3]
    return [(b * width, round(a[0] / width), ) for b, a in sorted(acc.items())]

def main():
    if sys.argv[1] == "--buckets":
        for run in sys.argv[2:]:
            print(os.path.basename(run), " ".join(f"{t//60:.0f}m:{g}" for t, g in buckets(run)))
        return
    print(f"{'run':40s} {'engines':>7s} {'window_s':>8s} {'gen_tok/s':>9s} {'steady':>9s} {'prefill_tok/s':>13s} {'kv%':>5s} {'hit%':>5s} {'running':>7s}")
    for run in sys.argv[1:]:
        eng = samples(run)
        if not eng: print(run, "no stats"); continue
        starts, ends, gen, pre, kv, hit, runn, n = [], [], 0.0, 0.0, 0.0, 0.0, 0.0, 0
        for e, s in eng.items():
            s.sort(); act = [x for x in s if x[3] > 0]
            if not act: continue
            starts.append(act[0][0]); ends.append(act[-1][0])
            for i in range(1, len(s)):
                dt = min(s[i][0] - s[i-1][0], 30)
                gen += s[i][2] * dt; pre += s[i][1] * dt
            for x in act: kv += x[5]; hit += x[6]; runn += x[3]; n += 1
        w = max(ends) - min(starts)
        b = [g for _, g in buckets(run) if g > 0][1:-1]; b.sort(); steady = b[len(b)//2] if b else 0
        print(f"{os.path.basename(run):40s} {len(eng):7d} {w:8.0f} {gen/w:9.1f} {steady:9d} {pre/w:13.0f} {kv/n:5.0f} {hit/n:5.0f} {runn/n:7.0f}")
main()
