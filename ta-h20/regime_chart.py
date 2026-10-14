"""regime_chart.py <points.json> [page.html] [--en]: blog-style concurrency regime chart.

y = steady-state engine-side generation throughput (tokens/s, both engines). Emits an inline SVG; with a
page path, splices it between <!-- regime-chart --> markers and rewrites the page in place.
"""
import json, sys

W, HT = 1440, 820
L, R, T, B = 150, 1330, 150, 650
XMAX, YMAX = 560, 1500
SERIES = {"global": ("VeRL Global LB", "#4b515e", "circle"),
          "ta-native": ("Dynamo native ThunderAgent", "#157f3d", "diamond"),
          "kv": ("Dynamo KV router", "#2d6ae0", "square")}
TXT = {
 "zh": dict(title="Claude Code subagent RL rollout：原生 ThunderAgent 高并发下维持吞吐，global LB 在 CC ≥ 256 跌到约 1/4",
            sub="Uni-Agent SWE-bench Verified ×32 · Claude Code 2.1.296（subagent 开启）· 8× H20 · Qwen3-Coder-30B-A3B · rollout-only · 每卡 KV 60 GiB",
            y="引擎生成吞吐，稳态 (tokens s⁻¹)", x="agent 并发数 (CC，同时在跑的 Claude Code session)", regime="高并发区 (CC ≥ 384)",
            pend="运行中", pendg="global 运行中", sub_note="虚线框点：第二轮，强制派 3 个 subagent 的 prompt",
            foot="* 第一轮名义 512 并发，但 Ray 默认 128 个 CPU 槽位只允许约 95 个 sandbox 同时运行，按实测并发标在 ≈95。纵轴为两台引擎 vLLM 调度器统计的生成 tok/s 的稳态中位数（10 分钟桶），计入每一个生成的 token，与 session 是否完成无关。",
            cap="参考 PyTorch blog 的 regime 图：横轴并发，纵轴引擎生成 tok/s。实线为默认 prompt。数据：<code>regime_points.json</code>，由 <code>engine_rate.py</code> 从各臂的 vLLM 统计日志算出。"),
 "en": dict(title="Claude Code subagent RL rollouts: native ThunderAgent holds throughput at high concurrency, global LB drops 4× past CC 256",
            sub="Uni-Agent SWE-bench Verified ×32 · Claude Code 2.1.296 (subagents on) · 8× H20 · Qwen3-Coder-30B-A3B · rollout-only · 60 GiB KV per GPU",
            y="Engine generation throughput, steady state (tokens s⁻¹)", x="Agent admission concurrency (CC, Claude Code sessions in flight)", regime="High-concurrency regime (CC ≥ 384)",
            pend="running", pendg="global running", sub_note="Dashed-outline points: sweep 2, prompt forcing 3 subagents",
            foot="* Sweep 1 was nominally CC 512, but Ray's default 128 CPU slots capped live sandboxes at about 95; plotted at the measured ≈95. Y is the steady-state median (10-min buckets) of the generation tok/s both engines' vLLM schedulers report, counting every generated token regardless of whether its session finished.",
            cap="Same construction as the PyTorch blog regime chart: concurrency on x, engine generation tok/s on y. Solid lines are the default prompt. Data: <code>regime_points.json</code>, computed by <code>engine_rate.py</code> from each arm's vLLM stats logs."),
}

def X(cc): return L + (R - L) * cc / XMAX
def Y(v): return B - (B - T) * v / YMAX

def marker(kind, x, y, color, hollow=False, dashed=False):
    fill = "var(--surface)" if hollow else color
    extra = ' stroke-dasharray="3 2.5"' if dashed else ""
    if kind == "circle": return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{fill}" stroke="{color}" stroke-width="2.2"{extra}/>'
    if kind == "square": return f'<rect x="{x-5.5:.1f}" y="{y-5.5:.1f}" width="11" height="11" fill="{fill}" stroke="{color}" stroke-width="2.2"{extra}/>'
    return f'<path d="M{x:.1f} {y-7.5:.1f} L{x+7.5:.1f} {y:.1f} L{x:.1f} {y+7.5:.1f} L{x-7.5:.1f} {y:.1f} Z" fill="{fill}" stroke="{color}" stroke-width="2.2"{extra}/>'

def svg(p, t):
    o = [f'<svg viewBox="0 0 {W} {HT}" width="100%" role="img" aria-label="throughput vs concurrency" style="font-family:var(--font-sans);display:block;max-width:100%">',
         f'<rect x="0" y="0" width="{W}" height="{HT}" fill="var(--surface)"/>',
         f'<rect x="{X(320):.1f}" y="{T-40}" width="{R-X(320):.1f}" height="{B-T+40}" fill="var(--good-soft)"/>',
         f'<text x="{(X(320)+R)/2:.1f}" y="{T-16}" text-anchor="middle" font-size="19" font-weight="600" fill="var(--good)">{t["regime"]}</text>']
    for v in range(0, YMAX + 1, 300):
        o.append(f'<line x1="{L}" y1="{Y(v):.1f}" x2="{R}" y2="{Y(v):.1f}" stroke="var(--line)" stroke-width="1"/>')
        o.append(f'<text x="{L-14}" y="{Y(v)+5:.1f}" text-anchor="end" font-size="16" fill="var(--ink-3)">{v:,}</text>')
    o.append(f'<text transform="translate(52 {(T+B)/2:.0f}) rotate(-90)" text-anchor="middle" font-size="17" font-weight="600" fill="var(--ink-2)">{t["y"]}</text>')
    o.append(f'<line x1="{L}" y1="{B}" x2="{R}" y2="{B}" stroke="var(--line-strong)" stroke-width="1.2"/>')
    for cc in (64, 128, 256, 384, 512):
        o.append(f'<text x="{X(cc):.1f}" y="{B+30}" text-anchor="middle" font-size="16" fill="var(--ink-2)">{cc}</text>')
    o.append(f'<text x="{X(95):.1f}" y="{B+30}" text-anchor="middle" font-size="14" fill="var(--ink-3)">≈95*</text>')
    o.append(f'<text x="{(L+R)/2:.0f}" y="{B+70}" text-anchor="middle" font-size="17" font-weight="600" fill="var(--ink-2)">{t["x"]}</text>')
    for cc in p.get("pending", []) + p.get("pending_global", []):
        o.append(f'<line x1="{X(cc):.1f}" y1="{T}" x2="{X(cc):.1f}" y2="{B}" stroke="var(--line-strong)" stroke-width="1" stroke-dasharray="3 6"/>')
        o.append(f'<text x="{X(cc):.1f}" y="{T+16}" text-anchor="middle" font-size="12.5" fill="var(--ink-3)">{t["pendg"] if cc in p.get("pending_global", []) else t["pend"]}</text>')
    for key, pts in p["default"].items():
        name, color, kind = SERIES[key]
        pts = sorted(pts, key=lambda d: d["cc"])
        o.append('<path d="' + " ".join(f'{"M" if i == 0 else "L"}{X(d["cc"]):.1f} {Y(d["v"]):.1f}' for i, d in enumerate(pts)) + f'" fill="none" stroke="{color}" stroke-width="3"/>')
        for d in pts:
            x, y = X(d["cc"]), Y(d["v"])
            o.append(marker(kind, x, y, color, hollow=(kind != "circle")))
            if key == "ta-native":
                o.append(f'<text x="{x:.1f}" y="{y-16:.1f}" text-anchor="middle" font-size="16" font-weight="600" fill="{color}">{d["v"]:,.0f}{d.get("ann","")}</text>')
            else:
                o.append(f'<text x="{x+13:.1f}" y="{y+24:.1f}" text-anchor="start" font-size="16" font-weight="600" fill="{color}">{d["v"]:,.0f}</text>')
    for key, pts in p.get("subagent_prompt", {}).items():
        name, color, kind = SERIES[key]
        for d in pts:
            x, y = X(d["cc"]), Y(d["v"])
            o.append(marker(kind, x, y, color, hollow=True, dashed=True))
            o.append(f'<text x="{x-13:.1f}" y="{y+5:.1f}" text-anchor="end" font-size="15" fill="{color}">{d["v"]:,.0f}</text>')
    o.append(f'<text x="{X(256)+14:.1f}" y="{Y(0)-12:.1f}" font-size="13.5" fill="var(--ink-3)">{t["sub_note"]}</text>')
    lx, ly = L, 92
    for key in ("global", "ta-native", "kv"):
        name, color, kind = SERIES[key]
        o.append(f'<line x1="{lx}" y1="{ly}" x2="{lx+34}" y2="{ly}" stroke="{color}" stroke-width="3"/>')
        o.append(marker(kind, lx + 17, ly, color, hollow=(kind != "circle")))
        o.append(f'<text x="{lx+44}" y="{ly+6}" font-size="17" font-weight="600" fill="var(--ink-2)">{name}</text>')
        lx += 44 + 11 * len(name) + 60
    o.append(f'<text x="{W/2:.0f}" y="40" text-anchor="middle" font-size="21" font-weight="600" fill="var(--ink)">{t["title"]}</text>')
    o.append(f'<text x="{W/2:.0f}" y="68" text-anchor="middle" font-size="17" fill="var(--ink-2)">{t["sub"]}</text>')
    f = t["foot"]; cut = f.rfind(" ", 0, 175) if " " in f[:175] else min(len(f), 100)
    if cut <= 0: cut = min(len(f), 100)
    o.append(f'<text x="{L}" y="{HT-30}" font-size="13" fill="var(--ink-3)">{f[:cut]}</text>')
    o.append(f'<text x="{L}" y="{HT-12}" font-size="13" fill="var(--ink-3)">{f[cut:].strip()}</text>')
    o.append('</svg>')
    return "\n".join(o)

def block(p, lang):
    t = TXT[lang]
    for d in p["default"]["ta-native"]:
        g = next((x for x in p["default"]["global"] if x["cc"] == d["cc"]), None)
        if g and d["cc"] >= 384: d["ann"] = f' (+{(d["v"]/g["v"]-1)*100:.0f}% vs global)'
    return ('<!-- regime-chart -->\n<figure style="margin:28px 0 8px;border:1px solid var(--line);border-radius:4px;overflow:hidden;background:var(--surface)">' + svg(p, t) +
            f'<figcaption style="padding:10px 16px;font-size:13px;color:var(--ink-3);border-top:1px solid var(--line)">{t["cap"]}</figcaption></figure>\n<!-- /regime-chart -->')

def splice(html, blk):
    a, b = html.index('<!-- regime-chart -->'), html.index('<!-- /regime-chart -->') + len('<!-- /regime-chart -->')
    return html[:a] + blk + html[b:]

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]; lang = "en" if "--en" in sys.argv else "zh"
    p = json.load(open(args[0])); blk = block(p, lang)
    if len(args) > 1:
        html = open(args[1]).read(); open(args[1], "w").write(splice(html, blk)); print("spliced", lang, len(blk))
    else: print(blk)
