"""build_pages.py <zh.html> <en.html>: insert/refresh the concurrency-scan section (table + chart) in both pages.

Reads regime_points.json and each run's summary.txt. The zh page gets the section inserted before the
old section 二 on first run (renumbering the rest); the en page carries a <!-- sweep-section --> placeholder.
Re-running replaces the section between <!-- sweep-section --> and <!-- /sweep-section -->.
"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(__file__))
import regime_chart

H = os.path.dirname(os.path.abspath(__file__))
P = json.load(open(f"{H}/regime_points.json"))

def summ(run):
    try: d = json.load(open(f"{H}/runs/{run}/summary.txt"))
    except Exception: return None
    return d

def pt(series, cc): return next((d for d in P["default"][series] if d["cc"] == cc), None)

TXT = {
 "zh": dict(h2="三 · 并发扫描：blog 口径的折线图", lead=(
   "按 blog 的做法把并发从 64 扫到 512（默认 prompt，每卡 KV 60 GiB，其余配置与第三轮相同）。CC 256/384/512 跑满 32×16=512 个 session，"
   "CC 64/128 跑两波（32×4、32×8），每个臂 3 小时墙钟上限。纵轴用<strong>引擎侧生成吞吐</strong>：两台 vLLM 引擎每 10 秒上报的调度器统计里的 "
   "generation tok/s，计入每一个生成的 token，与 session 是否结束无关；“稳态”取 10 分钟桶的中位数，“全程均值”把首尾爬坡和空转尾巴也算进去。"),
   cap="并发扫描：引擎侧吞吐与 session 结果", cols=["并发 CC", "TA 引擎 tok/s 稳态（全程）", "global 引擎 tok/s 稳态（全程）", "TA / global", "TA session 结束 / 完成", "global session 结束 / 完成", "TA session 均时", "global session 均时"],
   running="运行中", note95="≈95*", foot95="* 第一轮：名义 512 并发，被 Ray 槽位压到约 95 个 sandbox 同时在跑。512 行取第三轮，session 列按“前 512 个按开始时间”规则，trainer 口径见第五节。† 修复 9f32e49 之前的测量，重跑中。",
   why_h3="为什么早先版本的折线会“先掉再回升”",
   why=("本页 v6 到 v13 的折线用的是 <code>summarize_run.py</code> 的“model tok/s”：只统计计分窗口内<em>结束</em>的 session 保留下来的轨迹（"
        "<code>trajectory_selection=longest</code> 还会丢掉 subagent 自己的链），再除以窗口时长。global 在 CC 256/384 撞到 3 小时上限时还有 104 / 75 个 session 没结束，"
        "它们几个小时里生成的 token 全部不计数，而时间照算；到 CC 512，几乎所有 session 都在窗口内被 90 分钟超时切断而“结束”，token 就都算进去了。"
        "于是出现了 105 → 86 → 144 这条假的 V 形。换成引擎侧计数后，global 是单调的 1244 → 1305 → 313 → 284 → 284，和 blog 的形状一致；"
        "TA 在 64 到 512 全程 1219 到 1301，是一条水平线。修复 9f32e49 之前 TA 在 384/512 的全程均值只有 797 / 827：session 关闭时泄漏的 program 在末尾造成停滞；用修复后代码（804b377）复测后回到 1204 / 1196，稳态几乎不变（1231 → 1219、1255 → 1229）。CC 128 两臂也用 804b377 复测过一遍作交叉验证：TA 1279 → 1301，global 1300 → 1305，都在噪声内，说明修复没有改变低并发区、也没有碰到 global 臂。表里 128/256/384/512 的 TA 点和 128 的 global 点现在都是复测值。"
        "两套口径都保留在表里；session 口径的数字仍是 trainer 真正拿到的训练数据的速度，对比第三、四、五节。")),
 "en": dict(h2="3 · Concurrency scan: the blog-style regime chart", lead=(
   "Following the blog, concurrency is swept from 64 to 512 (default prompt, 60 GiB KV per GPU, otherwise the sweep-3 configuration). CC 256/384/512 run the full 32×16=512 sessions, "
   "CC 64/128 run two waves (32×4, 32×8); every arm has a 3-hour wall-clock cap. The y axis is <strong>engine-side generation throughput</strong>: the generation tok/s in the scheduler stats "
   "both vLLM engines log every 10 s, counting every generated token regardless of whether its session ended. \"Steady\" is the median of 10-minute buckets; \"window\" averages over the whole run including ramp-up and the idle tail."),
   cap="Concurrency scan: engine-side throughput and session outcomes", cols=["CC", "TA engine tok/s steady (window)", "global engine tok/s steady (window)", "TA / global", "TA sessions ended / finished", "global sessions ended / finished", "TA mean session", "global mean session"],
   running="running", note95="≈95*", foot95="* Sweep 1: nominally CC 512, capped by Ray slots at about 95 live sandboxes. The 512 row is sweep 3; its session columns follow the first-512-by-start rule, the trainer-faithful numbers are in section 5. † measured before fix 9f32e49, re-run pending.",
   why_h3="Why earlier versions of the chart dipped and came back",
   why=("Versions 6 to 13 of this page plotted the \"model tok/s\" from <code>summarize_run.py</code>: only trajectories kept from sessions that <em>ended</em> inside the scored window count "
        "(<code>trajectory_selection=longest</code> also drops the subagents' own chains), divided by the window length. When global hit the 3-hour cap at CC 256/384 it still had 104 / 75 sessions running; "
        "every token they generated over hours was dropped while their time counted. At CC 512 nearly every session \"ended\" inside the window through the 90-minute timeout, so their tokens counted. "
        "That produced the spurious 105 → 86 → 144 V shape. Counted engine-side, global is monotone, 1244 → 1305 → 313 → 284 → 284, the same shape as the blog; TA stays between 1219 and 1301 from 64 to 512, a flat line. "
        "Before fix 9f32e49 TA's window averages at 384/512 were only 797 / 827, an end-of-run stall caused by programs leaked at session close; re-measured on the fixed code (804b377) they return to 1204 / 1196 with the steady values nearly unchanged (1231 → 1219, 1255 → 1229). Both CC 128 arms were also re-run on 804b377 as a cross-check: TA 1279 → 1301, global 1300 → 1305, both within noise, so the fix changes neither the low-concurrency regime nor the global arm. The TA points at 128/256/384/512 and the global point at 128 are now the re-measured values. "
        "Both metrics stay in the table; the session-level number is still the rate at which the trainer actually receives training data, see sections 3 to 5.")),
}

def section(lang):
    t = TXT[lang]
    rows = []
    for cc in (95, 64, 128, 256, 384, 512):
        a, g = pt("ta-native", cc), pt("global", cc)
        sa, sg = (summ(a["run"]) if a else None), (summ(g["run"]) if g else None)
        def cell_rate(d): return f'{d["v"]:,} ({d["w"]:,}){"†" if d.get("pre_fix") else ""}' if d else t["running"]
        def cell_sess(s): return f'{s["sessions_done"]} / {s["finished_trajectories"]} (of {s["expected"]})'.replace("of", "共" if lang == "zh" else "of") if s else t["running"]
        def cell_lat(s): return f'{s["session_latency_mean_s"]:,.0f} s' if s else t["running"]
        ratio = f'{a["v"]/g["v"]:.2f}×' if a and g else t["running"]
        label = t["note95"] if cc == 95 else str(cc)
        rows.append(f'<tr><td>{label}</td><td class="num">{cell_rate(a)}</td><td class="num">{cell_rate(g)}</td><td class="num">{ratio}</td>'
                    f'<td class="num">{cell_sess(sa)}</td><td class="num">{cell_sess(sg)}</td><td class="num">{cell_lat(sa)}</td><td class="num">{cell_lat(sg)}</td></tr>')
    head = "".join(f'<th{" class=num" if i else ""}>{c}</th>' for i, c in enumerate(t["cols"]))
    return ("<!-- sweep-section -->\n" + f'<h2>{t["h2"]}</h2>\n<p>{t["lead"]}</p>\n<!-- regime-chart --><!-- /regime-chart -->\n'
            f'<div class="scroller"><table><caption>{t["cap"]}</caption><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>\n'
            f'<p style="font-size:13.5px;color:var(--ink-3)">{t["foot95"]}</p>\n<h3>{t["why_h3"]}</h3>\n<p>{t["why"]}</p>\n<!-- /sweep-section -->')

def put(html, sec):
    if "<!-- sweep-section -->" in html and "<!-- /sweep-section -->" in html:
        a, b = html.index("<!-- sweep-section -->"), html.index("<!-- /sweep-section -->") + len("<!-- /sweep-section -->")
        return html[:a] + sec + html[b:]
    if "<!-- sweep-section -->" in html:  # en placeholder
        return html.replace("<!-- sweep-section -->", sec)
    # zh first run: drop the old chart from section 一, renumber 二..六 -> 三..七, insert before the old 二
    if "<!-- regime-chart -->" in html:
        a, b = html.index("<!-- regime-chart -->"), html.index("<!-- /regime-chart -->") + len("<!-- /regime-chart -->")
        html = html[:a] + html[b:]
    for old, new in reversed([("二", "三"), ("三", "四"), ("四", "五"), ("五", "六"), ("六", "七")]):
        html = html.replace(f"<h2>{old} ·", f"<h2>{new} ·")
    i = html.index("<h2>三 ·")
    return html[:i] + sec + "\n\n" + html[i:]

zh, en = sys.argv[1], sys.argv[2]
hz = open(zh).read(); hz = put(hz, section("zh")); hz = regime_chart.splice(hz, regime_chart.block(json.loads(json.dumps(P)), "zh"))
hz = hz.replace("<span><b>完成</b> 2026-10-13 11:47</span>", "<span><b>更新</b> 2026-10-14</span>")
open(zh, "w").write(hz)
he = open(en).read()
if "/*CSS*/" in he: he = he.replace("/*CSS*/", hz[hz.index("<style>") + 7: hz.index("</style>")].split("</style>")[0] if False else re.search(r"<style>\n(  /\* Layout.*?)</style>", hz, re.S).group(1))
he = put(he, section("en")); he = regime_chart.splice(he, regime_chart.block(json.loads(json.dumps(P)), "en"))
open(en, "w").write(he)
print("zh", len(hz), "en", len(he), "h2:", re.findall(r"<h2>([^<]{1,12})", hz), re.findall(r"<h2>([^<]{1,12})", he))
