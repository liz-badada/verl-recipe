"""engine_rate.py <run>...: engine-side throughput from the scheduler stats each engine logs: vLLM every ~10 s,
SGLang every decode_log_interval steps (its "gen throughput" is likewise the mean over the interval since the
previous line; prefill tokens and cache hits come from its "Prefill batch" lines).

Counts every generated token (sessions that later timed out or were still running at the stop included),
so it is independent of how many sessions finished. Window = sampled time between the first and last stats line
with Running > 0. vLLM logs every ~10 s whether or not it decoded, so a gap longer than 30 s is a stall or a stray late
line and is capped at 30 s. SGLang logs only on decode, and its "gen throughput" already divides the tokens of the last
decode_log_interval steps by the wall time since the previous line (prefill-only stretches included), so its gaps are
real and are credited in full, capped at SG_CAP so a stats line long after the run cannot stretch the window.
"""
import glob, os, re, sys
from datetime import datetime

PAT = re.compile(r"Avg prompt throughput: ([\d.]+) tokens/s, Avg generation throughput: ([\d.]+) tokens/s, "
                 r"Running: (\d+) reqs, Waiting: (\d+) reqs, GPU KV cache usage: ([\d.]+)%, Prefix cache hit rate: ([\d.]+)%")
SG_DEC = re.compile(r"Decode batch, #running-req: (\d+), #token: \d+, token usage: ([\d.]+), .*?gen throughput \(token/s\): ([\d.]+), #queue-req: (\d+)")
SG_PRE = re.compile(r"Prefill batch, #new-seq: \d+, #new-token: (\d+), #cached-token: (\d+),")
G_TS = re.compile(r"\(vLLMHttpServer pid=(\d+)\).*?INFO (\d\d)-(\d\d) (\d\d):(\d\d):(\d\d)")
SG_TS = re.compile(r"\(SGLangHttpServer pid=(\d+)\).*?\[\d{4}-(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d) TP0\]")  # verl-native sglang, via ray
T_TS = re.compile(r"^\S*?(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)")
V_CAP, SG_CAP = 30.0, 900.0  # per-sample gap cap (s); each sample carries its own as field 7

PREFILL = {}  # run -> engine -> [new_tokens, cached_tokens] from SGLang prefill lines (vLLM reports rates instead)

def samples(run):
    out = {}  # engine -> [(t, prompt, gen, running, waiting, kv, hit)]
    files = glob.glob(f"{run}/dynamo/*/replica*_shard0.log")
    if files:
        for f in files:
            eng = os.path.basename(f).split("_")[0]
            for line in open(f, errors="replace"):
                ts = T_TS.match(line)
                if not ts: continue
                m = PAT.search(line)
                if m:
                    y, mo, d, hh, mm, ss = map(int, ts.groups())
                    out.setdefault(eng, []).append((datetime(y, mo, d, hh, mm, ss).timestamp(), *map(float, m.groups()), V_CAP))
                    continue
                m = SG_DEC.search(line)
                if m:
                    y, mo, d, hh, mm, ss = map(int, ts.groups()); running, usage, gen, queue = map(float, m.groups())
                    out.setdefault(eng, []).append((datetime(y, mo, d, hh, mm, ss).timestamp(), 0.0, gen, running, queue, usage * 100, 0.0, SG_CAP))
                    continue
                m = SG_PRE.search(line)
                if m:
                    p = PREFILL.setdefault(run, {}).setdefault(eng, [0, 0]); p[0] += int(m.group(1)); p[1] += int(m.group(2))
    else:  # global arms: the engines are ray actors, their stats lines reach console.log with the actor prefix
        for line in open(f"{run}/console.log", errors="replace"):
            m = PAT.search(line); ts = G_TS.search(line)
            if m and ts:
                pid, mo, d, hh, mm, ss = ts.groups()
                out.setdefault(pid, []).append((datetime(2026, int(mo), int(d), int(hh), int(mm), int(ss)).timestamp(), *map(float, m.groups()), V_CAP))
                continue
            ts = SG_TS.search(line)
            if not ts: continue
            pid, mo, d, hh, mm, ss = ts.groups(); t = datetime(2026, int(mo), int(d), int(hh), int(mm), int(ss)).timestamp()
            m = SG_DEC.search(line)
            if m:
                running, usage, gen, queue = map(float, m.groups())
                out.setdefault(pid, []).append((t, 0.0, gen, running, queue, usage * 100, 0.0, SG_CAP))
                continue
            m = SG_PRE.search(line)
            if m:
                p = PREFILL.setdefault(run, {}).setdefault(pid, [0, 0]); p[0] += int(m.group(1)); p[1] += int(m.group(2))
    return out

def buckets(run, width=600):
    """Per-bucket generation tok/s (both engines) along the active window, to see ramp-up and tail."""
    eng = samples(run); t0 = min(x[0] for s in eng.values() for x in s if x[3] > 0)
    acc = {}
    for s in eng.values():
        s.sort()
        for i in range(1, len(s)):
            dt = min(s[i][0] - s[i-1][0], s[i][7])
            # credit the tokens of a long SGLang gap to the buckets it spans, not only to the bucket of the line
            lo, hi = s[i][0] - dt, s[i][0]
            while lo < hi:
                b = int((lo - t0) // width); edge = min(hi, t0 + (b + 1) * width)
                a = acc.setdefault(b, [0.0, 0.0]); a[0] += s[i][2] * (edge - lo); lo = edge
            acc.setdefault(int((s[i][0] - t0) // width), [0.0, 0.0])[1] += s[i][3]
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
        spans = []
        for e, s in eng.items():
            s.sort(); act = [x for x in s if x[3] > 0]
            if not act: continue
            starts.append(act[0][0]); ends.append(act[-1][0])
            span = 0.0
            for i in range(1, len(s)):
                dt = min(s[i][0] - s[i-1][0], s[i][7])
                gen += s[i][2] * dt; pre += s[i][1] * dt
                if act[0][0] <= s[i][0] <= act[-1][0]: span += dt
            spans.append(span)
            for x in act: kv += x[5]; hit += x[6]; runn += x[3]; n += 1
            if e in PREFILL.get(run, {}):  # SGLang: computed prefill tokens and hit rate from its prefill lines
                new_t, cached = PREFILL[run][e]; pre += new_t  # computed tokens only, as vLLM counts them
                hit += 100.0 * cached / max(new_t + cached, 1) * len(act)
        # Window = sampled time between the first and last active stats line, each gap capped like the token sum
        # above (30 s for vLLM, SG_CAP for SGLang), so a stray stats line long after the run cannot stretch the denominator.
        w = max(spans)
        b = [g for _, g in buckets(run) if g > 0][1:-1]; b.sort(); steady = b[len(b)//2] if b else 0
        print(f"{os.path.basename(run):40s} {len(eng):7d} {w:8.0f} {gen/w:9.1f} {steady:9d} {pre/w:13.0f} {kv/n:5.0f} {hit/n:5.0f} {runn/n:7.0f}")
main()
