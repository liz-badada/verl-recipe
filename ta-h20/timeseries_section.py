"""timeseries_section.py <zh.html> <en.html>: throughput-over-time small multiples, one row of panels per stack
(vLLM 0.24, SGLang, vLLM 0.29), one panel per CC, ThunderAgent vs global LB, 30 s bins from the same engine stats
lines engine_rate.py uses. Also writes results/<run>/throughput_30s.csv for every booked run and a ramp table
(idle gap before the first request, minutes to reach 80% of the steady rate, first-10-min / steady).
Spliced between <!-- timeseries --> and <!-- /timeseries -->. t = 0 is the first stats line of either engine
(engines up); SGLang logs only on decode, so its t = 0 is the first decode and its idle gap is not observable."""
import json, os, sys
sys.argv, _argv = ["engine_rate.py", "--buckets"], sys.argv
import engine_rate as er
sys.argv = _argv
H = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(os.path.dirname(H), "ta-h20-harness", "results")
P = json.load(open(f"{H}/regime_points.json"))
STACKS = (("default", "vLLM 0.24.0", "vllm"), ("sglang", "SGLang 0.5.19", "sglang"), ("v029", "vLLM 0.29.0", "vllm"))
CCS = (64, 128, 256, 384, 512)
WIDTH, XMAX_MIN = 30, 180
COL = {"ta-native": "#157f3d", "global": "#4b515e"}

def pt(reg, ser, cc): return next((d for d in P.get(reg, {}).get(ser, []) if d["cc"] == cc), None)

def series(run):
    eng = er.samples(f"{H}/runs/{run}")
    t0 = min(x[0] for s in eng.values() for x in s); ta = min(x[0] for s in eng.values() for x in s if x[3] > 0)
    acc, seen = {}, set()
    for s in eng.values():
        s.sort()
        for i in range(1, len(s)):
            dt = min(s[i][0] - s[i-1][0], s[i][7]); lo, hi = s[i][0] - dt, s[i][0]
            while lo < hi:
                b = int((lo - t0) // WIDTH); edge = min(hi, t0 + (b + 1) * WIDTH); seen.add(b)
                acc[b] = acc.get(b, 0.0) + s[i][2] * (edge - lo); lo = edge
    # a bin no stats line covers is "no data" (the engine was not logging), not zero: engine_rate caps such gaps at 30 s
    ys = [round(acc.get(b, 0.0) / WIDTH) if b in seen else None for b in range(max(acc) + 1)]
    return ys, (ta - t0) / 60

def write_csv(run, ys):
    d = f"{R}/{run}"; os.makedirs(d, exist_ok=True)
    with open(f"{d}/throughput_30s.csv", "w") as f:
        f.write("t_s,gen_tok_s\n"); f.writelines(f"{i*WIDTH},{'' if y is None else y}\n" for i, y in enumerate(ys))

def ramp(ys, lag, v):
    i0 = int(lag * 60 // WIDTH); act = [y or 0 for y in ys[i0:]]
    r = next((i for i, y in enumerate(act) if y >= 0.8 * v), None)
    first10 = sum(act[:20]) / max(min(20, len(act)), 1)
    return (None if r is None else r * WIDTH / 60), first10 / v

DATA = {}  # (reg, ser, cc) -> dict(ys, lag, ramp, first10)
for reg, _, _ in STACKS:
    for cc in CCS:
        for ser in ("ta-native", "global"):
            d = pt(reg, ser, cc)
            if not d: continue
            ys, lag = series(d["run"]); write_csv(d["run"], ys); rp, f10 = ramp(ys, lag, d["v"])
            DATA[(reg, ser, cc)] = dict(ys=ys, lag=lag, ramp=rp, first10=f10, v=d["v"], w=d["w"])

TXT = {
 "zh": dict(h3="各并发档位的吞吐时间曲线（30 s 粒度）：冷启动在 H20 上是什么样",
            setup="同一批日志按 30 s 分桶：每块面板一个并发档位，绿色为 ThunderAgent，灰色为 global LB，虚线为各臂的窗口均值。横轴从引擎起来（第一条调度器统计行）算起；SGLang 只在解码时打统计，所以它的 0 点是第一次解码，看不到起跑前的空档。同一后端的面板共用纵轴。",
            legend=("ThunderAgent", "global LB"), x="分钟（自引擎起来）", pend="运行中", y="tok/s",
            th=("后端", "CC", "TA 起跑空档 (min)", "TA 到 80% 稳态 (min)", "TA 首 10 分钟 / 稳态", "global 到 80% 稳态 (min)", "global 首 10 分钟 / 稳态"),
            cap="数据：每个臂的 <code>results/&lt;run&gt;/throughput_30s.csv</code>，由 <code>timeseries_section.py</code> 用与 <code>engine_rate.py</code> 相同的统计行算出。起跑空档 = 引擎起来到第一条 Running &gt; 0 的统计行；到 80% 稳态 = 从第一个请求起、第一个 ≥ 0.8 × 稳态值的 30 s 桶。",
            result=lambda s: (f"H20 上有同样形状的冷启动，但只有几分钟：vLLM 两个栈里 ThunderAgent 的引擎起来后先空转 {s['lag']}，"
                              f"再用 {s['ramp_ta']}爬到稳态的 80%，并发越高爬得越慢；首 10 分钟均值已是稳态的 {s['f10_ta']}，摊到 2–3 小时的一个臂，窗口均值比稳态低 {s['cost']}。"
                              f"global LB 没有冷启动，它反过来：起跑就是峰值（{s['g_first']}），随着 session 上下文变长在 10–20 分钟内跌到低位——"
                              f"这是 CC ≥ 256 下它四分之一吞吐的来源，不是参数能调出来的。SGLang 栈上 ThunderAgent 没有可见空档，爬坡 {s['ramp_sg']}。")),
 "en": dict(h3="Throughput over time at each concurrency (30 s bins): what the cold start looks like on H20",
            setup="The same stats lines binned at 30 s: one panel per concurrency, green ThunderAgent, grey global LB, dashed lines the window means. t = 0 is the first scheduler stats line (engines up); SGLang logs stats only while decoding, so its t = 0 is the first decode and the idle gap before it is not observable. Panels of one backend share the y axis.",
            legend=("ThunderAgent", "global LB"), x="minutes since the engines came up", pend="running", y="tok/s",
            th=("Backend", "CC", "TA idle gap (min)", "TA to 80% of steady (min)", "TA first 10 min / steady", "global to 80% of steady (min)", "global first 10 min / steady"),
            cap="Data: <code>results/&lt;run&gt;/throughput_30s.csv</code> per arm, computed by <code>timeseries_section.py</code> from the same stats lines as <code>engine_rate.py</code>. Idle gap = engines up to the first stats line with Running &gt; 0; to 80% = first 30 s bin ≥ 0.8 × steady, counted from the first request.",
            result=lambda s: (f"H20 shows the same cold-start shape, but it lasts minutes: on both vLLM stacks the ThunderAgent engines idle for {s['lag']} after coming up, "
                              f"then take {s['ramp_ta']} to reach 80% of steady state, slower at higher concurrency; the first 10 minutes already average {s['f10_ta']} of steady, so over a 2–3 h arm the window mean sits {s['cost']} below steady. "
                              f"The global LB has no cold start; it does the opposite: it starts at its peak ({s['g_first']}) and falls to its low within 10–20 minutes as session contexts grow, "
                              f"which is where its quarter-rate at CC ≥ 256 comes from and is not a tuning matter. On SGLang the ThunderAgent arm shows no visible gap and ramps in {s['ramp_sg']}.")),
}

def fmt_min(x): return "—" if x is None else f"{x:.1f}"
def rng(vals, f, unit=""):
    vals = [v for v in vals if v is not None]
    if not vals: return "—"
    lo, hi = min(vals), max(vals)
    return f"{f(lo)}{unit}" if f(lo) == f(hi) else f"{f(lo)}–{f(hi)}{unit}"

def summary(lang):
    vt = [DATA[k] for k in DATA if k[0] in ("default", "v029") and k[1] == "ta-native"]
    st = [DATA[k] for k in DATA if k[0] == "sglang" and k[1] == "ta-native"]
    allt = vt + st
    g = [DATA[k] for k in DATA if k[1] == "global" and k[2] >= 256]
    m = " 分钟" if lang == "zh" else " min"
    return dict(lag=rng([d["lag"] for d in vt], lambda x: f"{x:.1f}", m),
                ramp_ta=rng([d["ramp"] for d in vt], lambda x: f"{x:g}", m),
                f10_ta=rng([d["first10"] for d in vt], lambda x: f"{x*100:.0f}", "%"),
                cost=rng([1 - d["w"] / d["v"] for d in allt if d["w"] < d["v"]], lambda x: f"{x*100:.0f}", "%"),
                g_first=rng([d["first10"] for d in g], lambda x: f"{x*100:.0f}", "%" + (" 的稳态值" if lang == "zh" else " of steady")),
                ramp_sg=rng([d["ramp"] for d in st], lambda x: f"{x:g}", m))

def panel_row(reg, label, lang):
    t = TXT[lang]; W, HT = 1440, 300; L0, PW, PH, TOP, GAP = 70, 258, 190, 58, 14
    ys_all = [y for (r, _, _), d in DATA.items() if r == reg for y in d["ys"] if y is not None]
    ymax = (max(ys_all) // 500 + 1) * 500 if ys_all else 2000
    o = [f'<svg viewBox="0 0 {W} {HT}" width="100%" role="img" aria-label="{label} throughput over time" style="font-family:var(--font-sans);display:block;max-width:100%">',
         f'<rect x="0" y="0" width="{W}" height="{HT}" fill="var(--surface)"/>',
         f'<text x="{L0}" y="26" font-size="17" font-weight="600" fill="var(--ink)">{label}</text>',
         f'<line x1="{L0+150}" y1="21" x2="{L0+178}" y2="21" stroke="{COL["ta-native"]}" stroke-width="2.4"/><text x="{L0+184}" y="26" font-size="14" fill="var(--ink-2)">{t["legend"][0]}</text>',
         f'<line x1="{L0+320}" y1="21" x2="{L0+348}" y2="21" stroke="{COL["global"]}" stroke-width="2.4"/><text x="{L0+354}" y="26" font-size="14" fill="var(--ink-2)">{t["legend"][1]}</text>',
         f'<text x="{W-24}" y="26" text-anchor="end" font-size="13" fill="var(--ink-3)">{t["x"]} · {t["y"]} 0–{ymax:,}</text>']
    for i, cc in enumerate(CCS):
        x0 = L0 + i * (PW + GAP); y0 = TOP; yb = y0 + PH
        def X(mn): return x0 + PW * min(mn, XMAX_MIN) / XMAX_MIN
        def Y(v): return yb - PH * min(v, ymax) / ymax
        o.append(f'<rect x="{x0}" y="{y0}" width="{PW}" height="{PH}" fill="none" stroke="var(--line)"/>')
        for v in range(0, ymax + 1, 500):
            o.append(f'<line x1="{x0}" y1="{Y(v):.1f}" x2="{x0+PW}" y2="{Y(v):.1f}" stroke="var(--line)" stroke-width="0.8"/>')
            if i == 0: o.append(f'<text x="{x0-8}" y="{Y(v)+4:.1f}" text-anchor="end" font-size="12" fill="var(--ink-3)">{v:,}</text>')
        for mn in (0, 60, 120, 180):
            anchor = "start" if mn == 0 else "end" if mn == XMAX_MIN else "middle"
            o.append(f'<text x="{X(mn):.1f}" y="{yb+16}" text-anchor="{anchor}" font-size="12" fill="var(--ink-3)">{mn}</text>')
        o.append(f'<text x="{x0+8}" y="{y0-8}" font-size="14" font-weight="600" fill="var(--ink)">CC {cc}</text>')
        legend, have = [], False
        for ser in ("global", "ta-native"):
            d = DATA.get((reg, ser, cc))
            if not d: continue
            have = True; c = COL[ser]
            o.append(f'<line x1="{x0}" y1="{Y(d["w"]):.1f}" x2="{x0+PW}" y2="{Y(d["w"]):.1f}" stroke="{c}" stroke-width="1" stroke-dasharray="4 4" opacity="0.8"/>')
            seg = []
            for k, y in enumerate(d["ys"] + [None]):
                if y is None or k * WIDTH / 60 > XMAX_MIN:
                    if len(seg) > 1: o.append(f'<polyline points="{" ".join(seg)}" fill="none" stroke="{c}" stroke-width="1.5" stroke-linejoin="round" opacity="{0.95 if ser == "ta-native" else 0.85}"/>')
                    seg = []
                else: seg.append(f"{X(k*WIDTH/60):.1f},{Y(y):.1f}")
            legend.append((c, d["w"]))
        for j, (c, w) in enumerate(reversed(legend)):  # ThunderAgent mean rightmost, global mean to its left
            o.append(f'<text x="{x0+PW-6-j*58}" y="{y0-8}" text-anchor="end" font-size="13" fill="{c}">{w:,}</text>')
        if not have:
            o.append(f'<text x="{x0+PW/2:.0f}" y="{y0+PH/2:.0f}" text-anchor="middle" font-size="13" fill="var(--ink-3)">{t["pend"]}</text>')
    o.append("</svg>")
    return "\n".join(o)

def table(lang):
    t = TXT[lang]
    rows = []
    for reg, label, _ in STACKS:
        for cc in CCS:
            a, g = DATA.get((reg, "ta-native", cc)), DATA.get((reg, "global", cc))
            if not a and not g: continue
            lag = "—" if reg == "sglang" or not a else f"{a['lag']:.1f}"
            rows.append("<tr>" + "".join(f'<td class="num">{c}</td>' for c in (
                label, cc, lag, fmt_min(a["ramp"]) if a else t["pend"], f"{a['first10']*100:.0f}%" if a else t["pend"],
                fmt_min(g["ramp"]) if g else t["pend"], f"{g['first10']*100:.0f}%" if g else t["pend"])) + "</tr>")
    head = "".join(f'<th class="num">{h}</th>' for h in t["th"])
    return f'<div class="scroller"><table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>\n<p style="font-size:13.5px;color:var(--ink-3)">{t["cap"]}</p>'

def section(lang):
    t = TXT[lang]
    figs = "\n".join(f'<figure style="margin:18px 0 8px;border:1px solid var(--line);border-radius:4px;overflow:hidden;background:var(--surface)">{panel_row(reg, label, lang)}</figure>' for reg, label, _ in STACKS)
    return f'<!-- timeseries -->\n<h3>{t["h3"]}</h3>\n<p>{t["setup"]}</p>\n{figs}\n{table(lang)}\n<p>{t["result"](summary(lang))}</p>\n<!-- /timeseries -->'

def splice(html, blk):
    a, b = html.index("<!-- timeseries -->"), html.index("<!-- /timeseries -->") + len("<!-- /timeseries -->")
    return html[:a] + blk + html[b:]

if __name__ == "__main__":
    for path, lang in zip(sys.argv[1:3], ("zh", "en")):
        h = open(path).read(); open(path, "w").write(splice(h, section(lang)))
    print("timeseries:", {k: (round(d["lag"], 1), d["ramp"], round(d["first10"], 2)) for k, d in DATA.items()})
