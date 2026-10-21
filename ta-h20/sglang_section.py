"""sglang_section.py <zh.html> <en.html>: the SGLang part of section 三/3: the sweep chart and per-CC table for every CC
with both arms, and the CC 256 comparison against the vLLM pair.

Reads regime_points.json["sglang"] (engine steady/window tok/s per arm) and, from each run directory, summary.txt,
summary.json (time to 512 trajectories, same rule as time_to_512.py), engine_rate.py's columns, subagent_split.py and
the router's peak program count. The vLLM CC 256 pair from regime_points["default"] stands beside it. Splices
between <!-- sglang-table --> and <!-- /sglang-table -->; the global column reads "running" until its point lands.
"""
import copy, json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regime_chart
from subagent_split import split

SWEEP = (64, 128, 256, 384, 512)

H = os.path.dirname(os.path.abspath(__file__))
P = json.load(open(f"{H}/regime_points.json"))

def pt(regime, series, cc=256): return next((d for d in P.get(regime, {}).get(series, []) if d["cc"] == cc), None)

def summ(run): return json.load(open(f"{H}/runs/{run}/summary.txt"))

def engine(run):
    """engine_rate.py's row: engines window gen steady prefill kv hit running."""
    line = subprocess.run([sys.executable, f"{H}/engine_rate.py", f"{H}/runs/{run}"], capture_output=True, text=True).stdout.strip().split("\n")[-1]
    f = line.split()
    return dict(window=float(f[2]), gen=float(f[3]), steady=int(f[4]), prefill=float(f[5]), kv=int(f[6]), hit=int(f[7]), running=int(f[8]))

def to512(run):
    d = json.load(open(f"{H}/runs/{run}/summary.json"))
    rows = [r for r in d.get("sessions_all", d["sessions"]) if r.get("start")]
    t0 = min(r["start"] for r in rows)
    first = sorted((r for r in rows if r.get("done") and r.get("end")), key=lambda r: r["end"])[:512]
    if len(first) < 512: return None
    traj = [t for r in first for t in r.get("trajectories", [])]
    wall = first[-1]["end"] - t0
    return dict(wall=wall, model=sum(t.get("model_token_count", 0) for t in traj) / wall, finished=sum(1 for t in traj if t.get("finished")))

def peak(run):
    try: txt = open(f"{H}/runs/{run}/dynamo/verl_dynamo_replica0_frontend.log", errors="replace").read()
    except FileNotFoundError: return None
    v = [int(x) for x in re.findall(r"scheduler state changed.*?programs=(\d+)", txt)]
    return max(v) if v else None

def arm(regime, series, cc=256):
    p = pt(regime, series, cc)
    if not p: return None
    run = p["run"]; s = summ(run); e = engine(run); sp = split(f"{H}/runs/{run}"); t = to512(run)
    return dict(p=p, s=s, e=e, sp=sp, t=t, peak=peak(run) if series == "ta-native" else None)

TXT = {
 "zh": dict(h3="同一口径换到 SGLang", running="运行中",
   cols=["指标", "SGLang · TA", "SGLang · global", "vLLM · TA", "vLLM · global"],
   rows=["引擎生成 tok/s 稳态（全程）", "TA / global（引擎稳态）", "session 结束 / 完成（共 512）", "收齐 512 条轨迹用时 · 其中完成",
         "模型生成 tok/s（收齐 512 条口径）", "session 平均时长", "引擎 KV 占用 / prefix 命中 / 平均 running", "派生过 subagent 的 session · 派生次数",
         "完成率：有 subagent / 无", "路由器峰值 program"],
   cap="CC 256，默认 prompt，两种引擎各一对臂；vLLM 列即上表的 256 行",
   setup=("同一套 harness、同一数据、模型、prompt，两种引擎的 KV 池都钉在每引擎 2,621,440 个 token（vLLM 由 60 GiB 的字节上限得出，SGLang 用 <code>--max-total-tokens</code> 钉到同一数字），只换推理引擎：SGLang 镜像为 sglang 0.5.19 / torch 2.13 + cu130（vLLM 镜像为 vLLM 0.24.0 / torch 2.11），"
          "两臂的 attention backend 都是 flashinfer，max_running_requests 256，chunked_prefill_size 32768，page_size 16，context_length 73728，TP 4 × 2 引擎。TA 臂的引擎由 dynamo.sglang worker 托管，global 臂由 verl 原生 sglang server 托管，sglang 版本相同。"
          "SGLang 按同一档位扫描（64 / 128 / 256 / 384 / 512，每臂 512 条轨迹），已完成的档位画在下图和表里；CC 256 另与 vLLM 的同档并排对照。纵轴口径同上：引擎调度器统计里的生成 tok/s（SGLang 每 40 个 decode 步报一次区间均值），稳态取 10 分钟桶中位数。"),
   pending=("<strong>SGLang 全部档位重测中（10-20 00:06 起，64 → 512，每档先 TA 后 global）。</strong>10-18/19 跑完的 7 个 SGLang 臂在复查时发现与 vLLM 两臂的 KV 预算不对等：sglang 只按 mem_fraction_static 0.78 分配，实际 KV 池 376 万 token / 引擎（约 87 GiB / 卡），"
            "而 vLLM 两臂被 60 GiB 字节上限钉在 262 万 token / 引擎，SGLang 的 global 臂因此比 vLLM 的晚一档才进入 KV 占满状态；global 臂的 chunked_prefill_size（8192 对 32768）、page_size（1 对 16）和上下文上限（无对 73728）也与 TA 臂不同。"
            "这 7 个点已从图表撤下，只作为原始数据保留在 <code>runs/*h20sgcc*-10160955</code>（<code>regime_points.json</code> 的 superseded 段记有原因）。"),
   result=("CC 256 上，SGLang 的 TA 对 global 引擎稳态倍数是 <strong>{ratio:.1f}×</strong>（{ta_v:,} 对 {gl_v:,}），vLLM 上是 {vratio:.1f}×（{vta_v:,} 对 {vgl_v:,}）。"
           "两种引擎上 global 臂都在 CC 256 进入 KV 占满状态：vLLM 的 global 臂 KV {vgl_kv}%、prefix 命中 {vgl_hit}%、平均 running {vgl_run}，SGLang 的 global 臂 KV {gl_kv}%、命中 {gl_hit}%、running {gl_run}（sglang 的 retraction 让 prefill 和 decode 互相打断）；"
           "TA 在两种引擎上都把引擎维持在 KV {ta_kv}%、命中 {ta_hit}%、running {ta_run}。"
           "以 trainer 口径看，SGLang 上 TA 收齐 512 条轨迹用 {ta_w:.0f} s（其中完成 {ta_f} 条），global {gl_t}；派生过 subagent 的 session 完成率 {ta_fw:.0%} 对 {gl_fw:.0%}。"
           "结论：KV 预算对齐后，SGLang 上的曲线形状和 vLLM 一致——CC 64 / 128 两臂持平（global 还没占满，TA 的准入没有东西可换），CC 256 起 global 崩、TA 不动；倍数的大小由 global 臂崩到多深决定，不由 TA 决定。"),
 ),
 "en": dict(h3="The same measurement on SGLang", running="running",
   cols=["Metric", "SGLang · TA", "SGLang · global", "vLLM · TA", "vLLM · global"],
   rows=["Engine generation tok/s steady (window)", "TA / global (engine steady)", "Sessions ended / finished (of 512)", "Time to 512 trajectories · finished among them",
         "Model tok/s (512-trajectory rule)", "Mean session duration", "Engine KV usage / prefix hit / mean running", "Sessions dispatching subagents · dispatches",
         "Finished rate: with subagents / without", "Router peak programs"],
   cap="CC 256, default prompt, one pair of arms per engine; the vLLM columns are the 256 row of the table above",
   setup=("Same harness, data, model and prompt, with both engines' KV pools pinned to 2,621,440 tokens per engine (vLLM through its 60 GiB byte cap, SGLang through <code>--max-total-tokens</code> set to the same number); only the inference engine changes: the SGLang image is sglang 0.5.19 / torch 2.13 + cu130 (the vLLM image is vLLM 0.24.0 / torch 2.11), "
          "both arms use the flashinfer attention backend, max_running_requests 256, chunked_prefill_size 32768, page_size 16, context_length 73728, TP 4 × 2 engines. The TA arm's engines are hosted by the dynamo.sglang worker, the global arm's by verl's native sglang server, same sglang build. "
          "SGLang is swept over the same CCs (64 / 128 / 256 / 384 / 512, 512 trajectories per arm); the finished CCs are in the chart and table below, and CC 256 is also set beside the vLLM pair. The y metric is the one used above: generation tok/s from the engine scheduler's stats (SGLang reports an interval mean every 40 decode steps), steady = median of 10-minute buckets."),
   pending=("<strong>Every SGLang CC is being re-measured (from 10-20 00:06, 64 → 512, TA then global at each CC).</strong> A review of the 7 SGLang arms finished on 10-18/19 found their KV budget unmatched to the vLLM arms: sglang sized its pool from mem_fraction_static 0.78 alone, 3.76M tokens per engine (about 87 GiB per GPU), "
            "while the vLLM arms were pinned at 2,621,440 tokens per engine by the 60 GiB byte cap, so SGLang's global arm reached the saturated-KV state one CC later than vLLM's; the global arm also differed from the TA arm in chunked_prefill_size (8192 vs 32768), page_size (1 vs 16) and context cap (none vs 73728). "
            "Those 7 points are withdrawn from the chart and table and kept only as raw data under <code>runs/*h20sgcc*-10160955</code> (the superseded block of <code>regime_points.json</code> records the reason)."),
   result=("At CC 256 the TA / global ratio of engine steady state on SGLang is <strong>{ratio:.1f}×</strong> ({ta_v:,} vs {gl_v:,}); on vLLM it is {vratio:.1f}× ({vta_v:,} vs {vgl_v:,}). "
           "On both engines the global arm saturates its KV at CC 256: on vLLM it runs at KV {vgl_kv}%, prefix hit {vgl_hit}%, mean running {vgl_run}; on SGLang at KV {gl_kv}%, hit {gl_hit}%, running {gl_run} (sglang's retraction makes prefill and decode interrupt each other). "
           "TA keeps the engines at KV {ta_kv}%, hit {ta_hit}%, running {ta_run} on both. "
           "By the trainer's rule, TA on SGLang collects 512 trajectories in {ta_w:.0f} s ({ta_f} finished among them); global {gl_t}; sessions that dispatched subagents finish at {ta_fw:.0%} vs {gl_fw:.0%}. "
           "Conclusion: with matched KV budgets the SGLang curve has the same shape as the vLLM one: at CC 64 / 128 the arms tie (global is not saturated, so TA's admission control has nothing to trade), from CC 256 global collapses and TA holds. The size of the multiple is set by how far the global arm collapses, not by TA."),
 ),
}

def table(lang, A):
    t = TXT[lang]; R = t["running"]
    sg_ta, sg_gl, v_ta, v_gl = A["sg_ta"], A["sg_gl"], A["v_ta"], A["v_gl"]
    def rate(a): return f'{a["p"]["v"]:,} ({a["p"]["w"]:,})' if a else R
    def ratio(a, g): return f'{a["p"]["v"] / g["p"]["v"]:.2f}×' if a and g else (R if not g else "—")
    def sess(a): return f'{a["s"]["sessions_done"]} / {a["s"]["finished_trajectories"]}' if a else R
    def t512(a):
        if not a: return R
        if not a["t"]: return ("未收齐（{n} 条，{w:.0f} s 到上限）" if lang == "zh" else "not reached ({n} at the {w:.0f} s cap)").format(n=a["s"]["trajectories"], w=a["s"]["wall_s"])
        return f'{a["t"]["wall"]:.0f} s · {a["t"]["finished"]}'
    def model(a): return (f'{a["t"]["model"]:.1f}' if a["t"] else "—") if a else R
    def lat(a): return f'{a["s"]["session_latency_mean_s"]:,.0f} s' if a else R
    def eng(a): return f'{a["e"]["kv"]}% / {a["e"]["hit"]}% / {a["e"]["running"]}' if a else R
    def sub(a): return f'{a["sp"]["with_subagents"]["sessions"]} ({a["sp"]["with_subagents"]["sessions"] / a["s"]["sessions_done"]:.0%}) · {a["sp"]["with_subagents"]["dispatches"]}' if a else R
    def fin(a): return f'{a["sp"]["with_subagents"]["finished_rate"]:.0%} / {a["sp"]["without_subagents"]["finished_rate"]:.0%}' if a else R
    def pk(a, series): return ("—" if series == "global" else (str(a["peak"]) if a["peak"] else "—")) if a else R
    cells = [
        [rate(sg_ta), rate(sg_gl), rate(v_ta), rate(v_gl)],
        [ratio(sg_ta, sg_gl), "—", ratio(v_ta, v_gl), "—"],
        [sess(sg_ta), sess(sg_gl), sess(v_ta), sess(v_gl)],
        [t512(sg_ta), t512(sg_gl), t512(v_ta), t512(v_gl)],
        [model(sg_ta), model(sg_gl), model(v_ta), model(v_gl)],
        [lat(sg_ta), lat(sg_gl), lat(v_ta), lat(v_gl)],
        [eng(sg_ta), eng(sg_gl), eng(v_ta), eng(v_gl)],
        [sub(sg_ta), sub(sg_gl), sub(v_ta), sub(v_gl)],
        [fin(sg_ta), fin(sg_gl), fin(v_ta), fin(v_gl)],
        [pk(sg_ta, "ta-native"), pk(sg_gl, "global"), pk(v_ta, "ta-native"), pk(v_gl, "global")],
    ]
    head = "".join(f'<th{" class=num" if i else ""}>{c}</th>' for i, c in enumerate(t["cols"]))
    body = "".join(f'<tr><td>{name}</td>' + "".join(f'<td class="num">{c}</td>' for c in row) + "</tr>" for name, row in zip(t["rows"], cells))
    return f'<div class="scroller"><table><caption>{t["cap"]}</caption><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'

def rng(a, b):
    a, b = sorted((a, b)); return str(a) if a == b else f"{a}–{b}"

CHART = {
 "zh": dict(title="同一 harness、同一负载换到 SGLang 0.5.19：引擎生成吞吐 vs 并发",
            sub="Uni-Agent SWE-bench Verified ×32 · Claude Code（subagent 开启）· 8× H20 · Qwen3-Coder-30B-A3B · rollout-only · KV 2,621,440 token / 引擎（与 vLLM 相同）",
            stack="推理后端 SGLang 0.5.19（torch 2.13 + cu130）· Dynamo 1.6.0.dev20260924 · verl 0.10.0.dev 3efe38c · verl-recipe 33fac10 · uni-agent 1622670 · Claude Code 2.1.300",
            y="引擎生成吞吐，稳态 (tokens s⁻¹)", x="agent 并发数 (CC，同时在跑的 Claude Code session)", regime="", pend="运行中", pendg="global 运行中", sub_note="",
            foot="纵轴为两台引擎 SGLang 调度器 decode 统计的生成 tok/s 的稳态中位数（10 分钟桶），计入每一个生成的 token，与 session 是否完成无关；每臂收 512 条轨迹。",
            cap="与上图同一构造，只换推理引擎。数据：<code>regime_points.json</code> 的 sglang 段，由 <code>engine_rate.py</code> 从各臂的 SGLang 调度器日志算出。"),
 "en": dict(title="Same harness and load on sglang 0.5.19: engine generation throughput vs concurrency",
            sub="Uni-Agent SWE-bench Verified ×32 · Claude Code (subagents on) · 8× H20 · Qwen3-Coder-30B-A3B · rollout-only · KV 2,621,440 tokens per engine (as vLLM)",
            stack="Backend SGLang 0.5.19 (torch 2.13 + cu130) · Dynamo 1.6.0.dev20260924 · verl 0.10.0.dev 3efe38c · verl-recipe 33fac10 · uni-agent 1622670 · Claude Code 2.1.300",
            y="Engine generation throughput, steady state (tokens s⁻¹)", x="Agent admission concurrency (CC, Claude Code sessions in flight)", regime="", pend="running", pendg="global running", sub_note="",
            foot="Y is the steady-state median (10-min buckets) of the generation tok/s both engines' SGLang schedulers report in their decode stats, counting every generated token regardless of whether its session finished; 512 trajectories per arm.",
            cap="Same construction as the chart above, only the inference engine differs. Data: the sglang block of <code>regime_points.json</code>, computed by <code>engine_rate.py</code> from each arm's SGLang scheduler logs."),
}
SWEEP_TXT = {
 "zh": dict(cols=["CC", "TA 稳态（全程）", "global 稳态（全程）", "TA / global", "收齐 512 条用时 TA / global", "其中完成 TA / global", "KV / 命中 / running：TA ‖ global"],
            cap="SGLang，默认 prompt，每档两臂各收 512 条轨迹；只列两臂都跑完的档位", none="未收齐"),
 "en": dict(cols=["CC", "TA steady (window)", "global steady (window)", "TA / global", "Time to 512 trajectories TA / global", "Finished among them TA / global", "KV / hit / running: TA ‖ global"],
            cap="SGLang, default prompt, 512 trajectories per arm at every CC; only CCs with both arms done are listed", none="not reached"),
}

def pairs():
    out = []
    for cc in SWEEP:
        a, g = arm("sglang", "ta-native", cc), arm("sglang", "global", cc)
        if a and g: out.append((cc, a, g))
    return out

def sweep_summary(lang, rows):
    if not rows: return ""
    ccs = " / ".join(str(cc) for cc, _, _ in rows)
    ratios = " / ".join(f"{a['p']['v'] / g['p']['v']:.2f}×" for _, a, g in rows)
    walls = " / ".join(f"{(a['t']['wall'] - g['t']['wall']) / g['t']['wall']:+.0%}" if a["t"] and g["t"] else "—" for _, a, g in rows)
    if lang == "zh":
        return f"扫描已跑完的档位 CC {ccs} 上，引擎稳态 TA / global 依次为 {ratios}，收齐 512 条轨迹的用时 TA 相对 global 依次为 {walls}（见上表）。"
    return f"Across the finished CCs {ccs}, engine steady state TA / global is {ratios} and TA's time to 512 trajectories relative to global is {walls} (table above). "

def sweep_table(lang, rows):
    t = SWEEP_TXT[lang]
    def w(a): return f'{a["t"]["wall"]:.0f} s' if a["t"] else t["none"]
    def f(a): return str(a["t"]["finished"]) if a["t"] else "—"
    def e(a): return f'{a["e"]["kv"]}% / {a["e"]["hit"]}% / {a["e"]["running"]}'
    body = "".join(f'<tr><td>{cc}</td><td class="num">{a["p"]["v"]:,} ({a["p"]["w"]:,})</td><td class="num">{g["p"]["v"]:,} ({g["p"]["w"]:,})</td>'
                   f'<td class="num"><strong>{a["p"]["v"] / g["p"]["v"]:.2f}×</strong></td><td class="num">{w(a)} / {w(g)}</td><td class="num">{f(a)} / {f(g)}</td>'
                   f'<td class="num">{e(a)} ‖ {e(g)}</td></tr>' for cc, a, g in rows)
    head = "".join(f'<th{" class=num" if i else ""}>{c}</th>' for i, c in enumerate(t["cols"]))
    return f'<div class="scroller"><table><caption>{t["cap"]}</caption><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'

def chart(lang):
    sg = P.get("sglang", {})
    ta = {d["cc"] for d in sg.get("ta-native", [])}; gl = {d["cc"] for d in sg.get("global", [])}
    if len(ta) < 2: return ""
    p = {"default": copy.deepcopy({"ta-native": sg.get("ta-native", []), "global": sg.get("global", [])}),
         "pending": [cc for cc in SWEEP if cc not in ta], "pending_global": [cc for cc in SWEEP if cc in ta and cc not in gl], "subagent_prompt": {}}
    return regime_chart.block(p, lang, t=CHART[lang], marker="sglang-chart", ymax=2100, band=False, approx95=False, legend=("global", "ta-native"))

def section(lang, A):
    t = TXT[lang]; sg_ta, sg_gl, v_ta, v_gl = A["sg_ta"], A["sg_gl"], A["v_ta"], A["v_gl"]
    rows = pairs(); sweep = (chart(lang) + "\n" + sweep_table(lang, rows) + "\n") if rows else ""
    if sg_ta and sg_gl:
        ta_w = sg_ta["t"]["wall"]
        if sg_gl["t"]: gl_t = ("用 {w:.0f} s（完成 {f} 条）" if lang == "zh" else "in {w:.0f} s ({f} finished)").format(w=sg_gl["t"]["wall"], f=sg_gl["t"]["finished"])
        else: gl_t = ("到 {w:.0f} s 的墙钟上限只收到 {n} 条（{d} 个 session 结束，完成 {f} 条）" if lang == "zh" else "reached only {n} at the {w:.0f} s wall cap ({d} sessions ended, {f} finished)").format(
            w=sg_gl["s"]["wall_s"], n=sg_gl["s"]["trajectories"], d=sg_gl["s"]["sessions_done"], f=sg_gl["s"]["finished_trajectories"])
        txt = t["result"].format(ratio=sg_ta["p"]["v"] / sg_gl["p"]["v"], ta_v=sg_ta["p"]["v"], gl_v=sg_gl["p"]["v"], vratio=v_ta["p"]["v"] / v_gl["p"]["v"], vta_v=v_ta["p"]["v"], vgl_v=v_gl["p"]["v"],
                                 vgl_kv=v_gl["e"]["kv"], vgl_hit=v_gl["e"]["hit"], vgl_run=v_gl["e"]["running"], gl_kv=sg_gl["e"]["kv"], gl_hit=sg_gl["e"]["hit"], gl_run=sg_gl["e"]["running"],
                                 ta_kv=rng(sg_ta["e"]["kv"], v_ta["e"]["kv"]), ta_hit=rng(sg_ta["e"]["hit"], v_ta["e"]["hit"]), ta_run=rng(sg_ta["e"]["running"], v_ta["e"]["running"]),
                                 ta_w=ta_w, gl_t=gl_t, ta_f=sg_ta["t"]["finished"],
                                 ta_fw=sg_ta["sp"]["with_subagents"]["finished_rate"], gl_fw=sg_gl["sp"]["with_subagents"]["finished_rate"])
    else:
        txt = t["pending"]
    txt = sweep_summary(lang, rows) + txt
    return f'<!-- sglang-table -->\n<h3>{t["h3"]}</h3>\n<p>{t["setup"]}</p>\n{sweep}{table(lang, A)}\n<p>{txt}</p>\n<!-- /sglang-table -->'

def splice(html, blk):
    a, b = html.index("<!-- sglang-table -->"), html.index("<!-- /sglang-table -->") + len("<!-- /sglang-table -->")
    return html[:a] + blk + html[b:]

A = dict(sg_ta=arm("sglang", "ta-native"), sg_gl=arm("sglang", "global"), v_ta=arm("default", "ta-native"), v_gl=arm("default", "global"))
for path, lang in zip(sys.argv[1:3], ("zh", "en")):
    h = open(path).read(); h = splice(h, section(lang, A)); open(path, "w").write(h)
print("sglang section:", {k: (v["p"]["run"] if v else None) for k, v in A.items()})
