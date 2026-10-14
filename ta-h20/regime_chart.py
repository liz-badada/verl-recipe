"""regime_chart.py <points.json> [page.html]: blog-style concurrency regime chart (model tok/s vs CC).

Emits an inline SVG; with a page path, splices it between <!-- regime-chart --> markers (or before
the second <h2>) and rewrites the page in place.
"""
import json, sys

W, HT = 1440, 820
L, R, T, B = 150, 1330, 150, 650
XMAX, YMAX = 560, 400
SERIES = {"global": ("VeRL Global LB", "#4b515e", "circle"),
          "ta-native": ("Dynamo native ThunderAgent", "#157f3d", "diamond"),
          "kv": ("Dynamo KV router", "#2d6ae0", "square")}

def X(cc): return L + (R - L) * cc / XMAX
def Y(v): return B - (B - T) * v / YMAX

def marker(kind, x, y, color, hollow=False):
    fill = "var(--surface)" if hollow else color
    if kind == "circle": return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{fill}" stroke="{color}" stroke-width="2.2"/>'
    if kind == "square": return f'<rect x="{x-5.5:.1f}" y="{y-5.5:.1f}" width="11" height="11" fill="{fill}" stroke="{color}" stroke-width="2.2"/>'
    return f'<path d="M{x:.1f} {y-7.5:.1f} L{x+7.5:.1f} {y:.1f} L{x:.1f} {y+7.5:.1f} L{x-7.5:.1f} {y:.1f} Z" fill="{fill}" stroke="{color}" stroke-width="2.2"/>'

def svg(p):
    o = [f'<svg viewBox="0 0 {W} {HT}" width="100%" role="img" aria-label="模型吞吐 vs 并发 折线图" style="font-family:var(--font-sans);display:block;max-width:100%">']
    o.append(f'<rect x="0" y="0" width="{W}" height="{HT}" fill="var(--surface)"/>')
    # high-concurrency regime shading
    o.append(f'<rect x="{X(320):.1f}" y="{T-40}" width="{R-X(320):.1f}" height="{B-T+40}" fill="var(--good-soft)"/>')
    o.append(f'<text x="{(X(320)+R)/2:.1f}" y="{T-16}" text-anchor="middle" font-size="19" font-weight="600" fill="var(--good)">高并发区 (CC ≥ 384)</text>')
    # grid + y axis
    for v in range(0, YMAX + 1, 100):
        o.append(f'<line x1="{L}" y1="{Y(v):.1f}" x2="{R}" y2="{Y(v):.1f}" stroke="var(--line)" stroke-width="1"/>')
        o.append(f'<text x="{L-14}" y="{Y(v)+5:.1f}" text-anchor="end" font-size="16" fill="var(--ink-3)">{v:,}</text>')
    o.append(f'<text transform="translate(52 {(T+B)/2:.0f}) rotate(-90)" text-anchor="middle" font-size="17" font-weight="600" fill="var(--ink-2)">模型生成吞吐 (tokens s⁻¹)</text>')
    # x axis
    o.append(f'<line x1="{L}" y1="{B}" x2="{R}" y2="{B}" stroke="var(--line-strong)" stroke-width="1.2"/>')
    for cc in (64, 128, 256, 384, 512):
        o.append(f'<text x="{X(cc):.1f}" y="{B+30}" text-anchor="middle" font-size="16" fill="var(--ink-2)">{cc}</text>')
    o.append(f'<text x="{X(95):.1f}" y="{B+30}" text-anchor="middle" font-size="14" fill="var(--ink-3)">≈95*</text>')
    o.append(f'<text x="{(L+R)/2:.0f}" y="{B+70}" text-anchor="middle" font-size="17" font-weight="600" fill="var(--ink-2)">agent 并发数 (CC，同时在跑的 Claude Code session)</text>')
    # pending points
    for cc in p.get("pending", []) + p.get("pending_global", []):
        o.append(f'<line x1="{X(cc):.1f}" y1="{T}" x2="{X(cc):.1f}" y2="{B}" stroke="var(--line-strong)" stroke-width="1" stroke-dasharray="3 6"/>')
        o.append(f'<text x="{X(cc):.1f}" y="{T+16}" text-anchor="middle" font-size="12.5" fill="var(--ink-3)">{"global 运行中" if cc in p.get("pending_global", []) else "运行中"}</text>')
    # default-prompt series (solid lines)
    for key, pts in p["default"].items():
        name, color, kind = SERIES[key]
        pts = sorted(pts, key=lambda d: d["cc"])
        path = " ".join(f'{"M" if i == 0 else "L"}{X(d["cc"]):.1f} {Y(d["v"]):.1f}' for i, d in enumerate(pts))
        o.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="3"/>')
        for d in pts:
            x, y = X(d["cc"]), Y(d["v"])
            o.append(marker(kind, x, y, color, hollow=(kind != "circle")))
            dy = -16 if key == "ta-native" else 30
            o.append(f'<text x="{x:.1f}" y="{y+dy:.1f}" text-anchor="middle" font-size="16" font-weight="600" fill="{color}">{d["v"]:,.0f}{d.get("ann","")}</text>')
    # subagent-prompt markers (hollow, dashed connector to its own x tick)
    for key, pts in p.get("subagent_prompt", {}).items():
        name, color, kind = SERIES[key]
        for d in pts:
            x, y = X(d["cc"]), Y(d["v"])
            o.append(marker(kind, x, y, color, hollow=True).replace('stroke-width="2.2"', 'stroke-width="2.2" stroke-dasharray="3 2.5"'))
            o.append(f'<text x="{x+14:.1f}" y="{y+5:.1f}" font-size="15" fill="{color}">{d["v"]:,.0f}</text>')
    o.append(f'<text x="{X(256)+14:.1f}" y="{Y(0)-12:.1f}" font-size="13.5" fill="var(--ink-3)">虚线框点：第二轮，强制派 3 个 subagent 的 prompt</text>')
    # legend
    lx, ly = L, 92
    for key in ("global", "ta-native", "kv"):
        name, color, kind = SERIES[key]
        o.append(f'<line x1="{lx}" y1="{ly}" x2="{lx+34}" y2="{ly}" stroke="{color}" stroke-width="3"/>')
        o.append(marker(kind, lx + 17, ly, color, hollow=(kind != "circle")))
        o.append(f'<text x="{lx+44}" y="{ly+6}" font-size="17" font-weight="600" fill="var(--ink-2)">{name}</text>')
        lx += 44 + 11 * len(name) + 60
    o.append(f'<text x="{W/2:.0f}" y="40" text-anchor="middle" font-size="24" font-weight="600" fill="var(--ink)">原生 ThunderAgent 在高并发下维持 rollout 吞吐，global LB 在 512 并发下跌去 57%</text>')
    o.append(f'<text x="{W/2:.0f}" y="68" text-anchor="middle" font-size="17" fill="var(--ink-2)">Uni-Agent SWE-bench Verified ×32 · Claude Code 2.1.296 · 8× H20 · Qwen3-Coder-30B-A3B · rollout-only · 每卡 KV 60 GiB</text>')
    o.append(f'<text x="{L}" y="{HT-22}" font-size="13.5" fill="var(--ink-3)">* 第一轮名义 512 并发，但 Ray 默认 128 个 CPU 槽位只允许约 95 个 sandbox 同时运行，按实测并发标在 ≈95。</text>')
    o.append('</svg>')
    return "\n".join(o)

def main():
    p = json.load(open(sys.argv[1]))
    for d in p["default"]["ta-native"]:
        g = next((x for x in p["default"]["global"] if x["cc"] == d["cc"]), None)
        if g and d["cc"] >= 384: d["ann"] = f' (+{(d["v"]/g["v"]-1)*100:.0f}% vs global)'
    block = '<!-- regime-chart -->\n<figure style="margin:28px 0 8px;border:1px solid var(--line);border-radius:4px;overflow:hidden;background:var(--surface)">' + svg(p) + \
            '<figcaption style="padding:10px 16px;font-size:13px;color:var(--ink-3);border-top:1px solid var(--line)">参考 PyTorch blog 的 regime 图：横轴并发，纵轴模型生成 tok/s。实线为默认 prompt；CC 64 的默认 prompt 点由 <code>sweep_cc.sh</code> 补跑中，完成后更新。数据：<code>regime_points.json</code>。</figcaption></figure>\n<!-- /regime-chart -->'
    if len(sys.argv) > 2:
        html = open(sys.argv[2]).read()
        if '<!-- regime-chart -->' in html:
            a, b = html.index('<!-- regime-chart -->'), html.index('<!-- /regime-chart -->') + len('<!-- /regime-chart -->')
            html = html[:a] + block + html[b:]
        else:
            i = html.index('<h2>二 ·')
            html = html[:i] + block + '\n\n' + html[i:]
        open(sys.argv[2], 'w').write(html)
        print("spliced", len(block), "bytes")
    else:
        print(block)
main()
