"""subagent_gain.py <zh.html> <en.html>: the "how much of the gain is the subagent work" figure.

Inserted between <!-- subagent-gain --> and <!-- /subagent-gain --> at the end of the concurrency-scan
section (build_pages.py leaves the markers in place). Two panels on the forced-subagent traffic:
  A. the ladder global -> TA (identity ignored) -> TA (program per agent, no parent) -> TA (full tree),
     steady engine tok/s at CC 256; rungs without a run yet are drawn as pending;
  B. what the subagent correctness work (release on return, no leak) changed on the same wall budget:
     sessions finished and post-budget idle minutes, before and after fix 9f32e49.
Numbers come from regime_points.json and the runs' summaries; the idle minutes from the engine stats.
"""
import json, os, sys

H = os.path.dirname(os.path.abspath(__file__))
P = json.load(open(f"{H}/regime_points.json"))


def pt(regime, series, cc):
    return next((d for d in P[regime][series] if d["cc"] == cc), None)


def done(run):
    try:
        return json.load(open(f"{H}/runs/{run}/summary.txt"))["sessions_done"]
    except Exception:
        return None


def ablation_run(mode):
    """The ablation arm's steady tok/s once its run has landed (regime_points: ablation list)."""
    return next((d for d in P.get("ablation", []) if d.get("mode") == mode), None)


# Panel A: forced-subagent prompt, CC 256.
G = pt("subagent_prompt", "global", 256)
T = pt("subagent_prompt", "ta-native", 256)
OFF, ISO = ablation_run("off"), ablation_run("isolated")

# Panel B: the same arm before and after the release/leak fix (9f32e49), same wall-clock budget.
# idle = minutes the engines kept stats lines with Running > 0 but no generation after the budget (gaps > 30 s).
FIX = [
    dict(label_zh="默认 prompt · CC 384", label_en="default prompt · CC 384", pre="ta-native-h20cc384-10131520", post="ta-native-h20cc384-10141340", idle_pre=57, idle_post=1, tokwall_pre=1225, tokwall_post=1227),
    dict(label_zh="默认 prompt · CC 512", label_en="default prompt · CC 512", pre="ta-native-h20cc512-10130706", post="ta-native-h20cc512-10141340", idle_pre=42, idle_post=1, tokwall_pre=1166, tokwall_post=1172),
    dict(label_zh="强制 subagent · CC 256", label_en="forced subagents · CC 256", pre="ta-native-h20sub-10122136", post="ta-native-h20subcc256-10141340", idle_pre=1, idle_post=1, tokwall_pre=1262, tokwall_post=1194),
]
for f in FIX:
    f["done_pre"], f["done_post"] = done(f["pre"]), done(f["post"])

TXT = {
    "zh": dict(
        h3="subagent 这块优化到底换回多少：把 TA 本身的收益和 subagent 专项分开",
        lead=("上面 3.9–4.5× 是整套 ThunderAgent 对 global LB 的差距，里面既有 TA 本来就有的准入控制，也有这次为 Claude Code subagent 做的事。"
              "两者在同一份强制 subagent 流量（CC 256，512 个 session，约 67% 的 session 各派 3 个 subagent）上按阶梯拆：每一级只多开一样东西。"
              "两端已经测过，中间两级（TA 不认 subagent；TA 认 subagent 但不告诉 router 父子关系）排在 TA 64 重测之后跑，各 3 小时，跑完直接填进这张图。"),
        capA="A · 阶梯：强制 subagent，CC 256，引擎稳态 tok/s",
        rungs=["global LB（基线）", "TA · 不认 subagent（请求都算在父 session 的 program 上，上游 TA 的行为）", "TA · 每个 subagent 一个 program，用完即释放，不报父子", "TA · 完整（+ 兄弟同置 / 根绑定）"],
        pending="待测", measured="已测",
        capB="B · subagent 正确性修复（release-on-return、不泄漏 program）在同一墙钟预算内换回的东西",
        colsB=["场景", "预算内 tok/s（修前 → 修后）", "跑完的 session / 512（修前 → 修后）", "预算后引擎空转（分钟）"],
        noteB=("修前的 TA 已经按 subagent 建 program，只是 session 关闭时泄漏；所以这一行量的是\"修复泄漏\"的收益，不是\"认 subagent 对比不认\"的收益——那是面板 A 的第二级。"
               "在预算内，修前修后生成的 token 几乎一样多；差别全在尾巴：泄漏的 program 让引擎在预算用完后空转 42–57 分钟，少跑完 55–147 个 session。"),
        capC="C · 剂量反应：subagent 负载翻倍，两臂稳态都只动了 3%",
        colsC=["CC 256", "subagent dispatch 数", "派 subagent 的 session", "TA 稳态", "global 稳态", "TA / global"],
        rowsC=[["默认 prompt", "447", "281 / 512", "1241", "319", "3.9×"], ["强制 subagent", "1081", "351 / 511", "1201", "311", "3.9×"]],
        noteC=("如果兄弟同置换回的 KV 在稳态里占大头，subagent 多 2.3 倍时 TA 应该相对 global 拉开，实际倍数没变。"
               "所以稳态上 subagent 放置优化的份额不会超过几个百分点；它的价值在面板 B 那一列：树一多 TA 不停滞、不丢 session。精确份额等面板 A 填满。"),
    ),
    "en": dict(
        h3="How much of the gain is the subagent work: separating ThunderAgent itself from the subagent-specific part",
        lead=("The 3.9–4.5× above is the whole ThunderAgent stack against the global LB: the admission control TA always had, plus what was built here for Claude Code subagents. "
              "The two are separated on one forced-subagent traffic (CC 256, 512 sessions, about 67% of them dispatching 3 subagents each) as a ladder where each rung adds one thing. "
              "Both ends are measured; the two middle rungs (TA ignoring subagents; TA with a program per agent but no parent announced to the router) are queued after the TA 64 re-run, 3 hours each, and drop straight into this figure."),
        capA="A · Ladder: forced subagents, CC 256, steady engine tok/s",
        rungs=["global LB (baseline)", "TA · subagents ignored (every turn charged to the parent session's program, as upstream TA behaves)", "TA · a program per subagent, released on return, no parent announced", "TA · full (+ sibling co-location / root pinning)"],
        pending="pending", measured="measured",
        capB="B · What the subagent correctness work (release on return, no leaked programs) bought inside the same wall-clock budget",
        colsB=["Scenario", "tok/s inside the budget (before → after)", "Sessions finished / 512 (before → after)", "Engine idle after the budget (min)"],
        noteB=("The pre-fix TA already created a program per subagent; it leaked them at session close. So this row measures the leak fix, not subagent-aware vs unaware, which is rung 2 of panel A. "
               "Inside the budget both versions generated nearly the same tokens; the difference is all in the tail: leaked programs kept the engines idling 42–57 minutes past the budget, and 55–147 fewer sessions finished."),
        capC="C · Dose response: 2.3× the subagent load moved both arms' steady state by 3%",
        colsC=["CC 256", "Subagent dispatches", "Sessions dispatching", "TA steady", "global steady", "TA / global"],
        rowsC=[["default prompt", "447", "281 / 512", "1241", "319", "3.9×"], ["forced subagents", "1081", "351 / 511", "1201", "311", "3.9×"]],
        noteC=("If sibling co-location bought a large share of the steady state, 2.3× more subagents should widen TA's lead over global; the ratio did not move. "
               "So the placement part is worth at most a few percent of steady throughput; its value is panel B's columns: TA keeps going and keeps its sessions once trees pile up. The exact split arrives when panel A fills in."),
    ),
}


def ladder_svg(t):
    rows = [(t["rungs"][0], G["v"] if G else None, "var(--ink-3)", G["run"] if G else ""),
            (t["rungs"][1], OFF["v"] if OFF else None, "var(--accent)", OFF["run"] if OFF else ""),
            (t["rungs"][2], ISO["v"] if ISO else None, "var(--accent)", ISO["run"] if ISO else ""),
            (t["rungs"][3], T["v"] if T else None, "var(--good)", T["run"] if T else "")]
    vmax = 1400
    x0, x1 = 20, 700
    def X(v): return x0 + (x1 - x0) * v / vmax
    o = [f'<svg viewBox="0 0 760 {40 + 64 * len(rows)}" role="img" aria-label="{t["capA"]}" style="width:100%;height:auto;max-width:100%">']
    for g in (0, 350, 700, 1050, 1400):
        o.append(f'<line x1="{X(g):.1f}" y1="8" x2="{X(g):.1f}" y2="{20 + 64 * len(rows)}" stroke="var(--line)" stroke-width="1"/>')
        o.append(f'<text x="{X(g):.1f}" y="{34 + 64 * len(rows)}" text-anchor="middle" font-size="11.5" font-family="var(--font-mono)" fill="var(--ink-3)">{g}</text>')
    for i, (label, v, color, run) in enumerate(rows):
        y = 16 + 64 * i
        o.append(f'<text x="{x0}" y="{y + 10}" font-size="12.5" font-family="var(--font-sans)" fill="var(--ink-2)">{label}</text>')
        if v is None:
            o.append(f'<rect x="{x0}" y="{y + 18}" width="{X(600) - x0:.1f}" height="22" rx="2" fill="none" stroke="var(--line-strong)" stroke-dasharray="5 4"/>')
            o.append(f'<text x="{x0 + 10}" y="{y + 33}" font-size="12.5" font-family="var(--font-sans)" fill="var(--ink-3)">{t["pending"]}</text>')
        else:
            o.append(f'<rect x="{x0}" y="{y + 18}" width="{X(v) - x0:.1f}" height="22" rx="2" fill="{color}"/>')
            o.append(f'<text x="{X(v) + 8:.1f}" y="{y + 33}" font-size="13" font-family="var(--font-mono)" font-weight="500" fill="var(--ink)">{v:,}</text>')
            o.append(f'<text x="{x1 + 54}" y="{y + 33}" text-anchor="end" font-size="10.5" font-family="var(--font-mono)" fill="var(--ink-3)">{run}</text>')
    o.append("</svg>")
    return "\n".join(o)


def fix_table(t, lang):
    rows = []
    for f in FIX:
        dp, dq = f["done_pre"], f["done_post"]
        rows.append(f'<tr><td>{f["label_" + lang]}</td><td class="num">{f["tokwall_pre"]:,} → {f["tokwall_post"]:,}</td>'
                    f'<td class="num">{dp} → {dq}' + (f' <span style="color:var(--good)">(+{dq - dp})</span>' if dp is not None and dq is not None and dq > dp else "") + '</td>'
                    f'<td class="num">{f["idle_pre"]} → {f["idle_post"]}</td></tr>')
    head = "".join(f"<th{' class=\"num\"' if i else ''}>{c}</th>" for i, c in enumerate(t["colsB"]))
    return f'<div class="scroller"><table><caption>{t["capB"]}</caption><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def dose_table(t):
    head = "".join(f"<th{' class=\"num\"' if i else ''}>{c}</th>" for i, c in enumerate(t["colsC"]))
    body = "".join("<tr>" + "".join(f"<td{' class=\"num\"' if i else ''}>{c}</td>" for i, c in enumerate(r)) + "</tr>" for r in t["rowsC"])
    return f'<div class="scroller"><table><caption>{t["capC"]}</caption><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def section(lang):
    t = TXT[lang]
    return ("<!-- subagent-gain -->\n"
            f'<h3>{t["h3"]}</h3>\n<p>{t["lead"]}</p>\n'
            f'<figure><figcaption style="margin:0 0 8px">{t["capA"]}</figcaption>{ladder_svg(t)}</figure>\n'
            f'{fix_table(t, lang)}\n<p style="font-size:13.5px;color:var(--ink-3)">{t["noteB"]}</p>\n'
            f'{dose_table(t)}\n<p style="font-size:13.5px;color:var(--ink-3)">{t["noteC"]}</p>\n'
            "<!-- /subagent-gain -->")


def put(html, lang):
    a, b = html.index("<!-- subagent-gain -->"), html.index("<!-- /subagent-gain -->") + len("<!-- /subagent-gain -->")
    return html[:a] + section(lang) + html[b:]


if __name__ == "__main__":
    for path, lang in zip(sys.argv[1:3], ("zh", "en")):
        html = open(path, encoding="utf-8").read()
        out = put(html, lang)
        open(path, "w", encoding="utf-8").write(out)
        print(lang, len(out), "ladder:", [G and G["v"], OFF and OFF["v"], ISO and ISO["v"], T and T["v"]])
