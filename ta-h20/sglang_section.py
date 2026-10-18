"""sglang_section.py <zh.html> <en.html>: the SGLang CC 256 comparison table inside section 三/3.

Reads regime_points.json["sglang"] (engine steady/window tok/s per arm) and, from each run directory, summary.txt,
summary.json (time to 512 trajectories, same rule as time_to_512.py), engine_rate.py's columns, subagent_split.py and
the router's peak program count. The vLLM CC 256 pair from regime_points["default"] stands beside it. Splices
between <!-- sglang-table --> and <!-- /sglang-table -->; the global column reads "running" until its point lands.
"""
import json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from subagent_split import split

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

def arm(regime, series):
    p = pt(regime, series)
    if not p: return None
    run = p["run"]; s = summ(run); e = engine(run); sp = split(f"{H}/runs/{run}"); t = to512(run)
    return dict(p=p, s=s, e=e, sp=sp, t=t, peak=peak(run) if series == "ta-native" else None)

TXT = {
 "zh": dict(h3="同一口径换到 SGLang：CC 256", running="运行中",
   cols=["指标", "SGLang · TA", "SGLang · global", "vLLM · TA", "vLLM · global"],
   rows=["引擎生成 tok/s 稳态（全程）", "TA / global（引擎稳态）", "session 结束 / 完成（共 512）", "收齐 512 条轨迹用时 · 其中完成",
         "模型生成 tok/s（收齐 512 条口径）", "session 平均时长", "引擎 KV 占用 / prefix 命中 / 平均 running", "派生过 subagent 的 session · 派生次数",
         "完成率：有 subagent / 无", "路由器峰值 program"],
   cap="CC 256，默认 prompt，两种引擎各一对臂；vLLM 列即上表的 256 行",
   setup=("同一套 harness、同一数据、模型、prompt 和每卡约 60 GiB 的 KV 预算，只换推理引擎：SGLang 镜像为 sglang 0.5.19 / torch 2.13 + cu130（vLLM 镜像为 vLLM 0.24.0 / torch 2.11），"
          "两臂的 attention backend 都是 flashinfer，mem_fraction_static 0.78，max_running_requests 256，TP 4 × 2 引擎。TA 臂的引擎由 dynamo.sglang worker 托管，global 臂由 verl 原生 sglang server 托管，sglang 版本相同。"
          "SGLang 只跑了 CC 256 一个点。纵轴口径同上：引擎调度器统计里的生成 tok/s（SGLang 每 40 个 decode 步报一次区间均值），稳态取 10 分钟桶中位数。"),
   pending=("global 臂复测中：首跑 10-18 11:18–13:22 完成 508 / 512 个 session（收齐 512 条轨迹 3925 s、完成 246 条，trainer 口径 319 tok/s），但 verl 原生 sglang server 以 <code>log_level=error</code> 启动，没有留下引擎统计，不能进表；"
            "已改为 <code>engine_kwargs.sglang.log_level=info</code> 于 13:36 重跑，预计 15:45 出结果。首跑数据保留在 <code>runs/global-h20sgcc256-10160955-nostats</code>。"),
   result=("SGLang 上 TA 对 global 的引擎稳态倍数是 <strong>{ratio:.2f}×</strong>（{ta_v:,} 对 {gl_v:,}），vLLM 上是 {vratio:.2f}×（{vta_v:,} 对 {vgl_v:,}）。差别全在 global 臂：vLLM 的 global 臂在 CC 256 跑在 KV {vgl_kv}%、prefix 命中 {vgl_hit}%、平均 running {vgl_run} 的状态，"
           "SGLang 的 global 臂为 KV {gl_kv}%、命中 {gl_hit}%、running {gl_run}；TA 在两种引擎上都把引擎维持在 KV {ta_kv}%、命中 {ta_hit}%、running {ta_run}。"
           "以 trainer 口径看，SGLang 上 TA 收齐 512 条轨迹用 {ta_w:.0f} s，global 用 {gl_w:.0f} s（{dw:+.0%}），其中完成的轨迹 {ta_f} 对 {gl_f}；派生过 subagent 的 session 完成率 {ta_fw:.0%} 对 {gl_fw:.0%}。"
           "结论：TA 的引擎侧收益大小取决于引擎本身在无准入控制时的表现；vLLM 0.24 上的 4 倍主要是 global 臂在这台机器上的 KV 占满状态造成的，SGLang 0.5.19 上同一负载下 global 没有进入那种状态，TA 的收益收敛为 {ratio:.2f}× 的引擎吞吐和 {dwabs:.0%} 的收齐时间。"),
 ),
 "en": dict(h3="The same measurement on SGLang: CC 256", running="running",
   cols=["Metric", "SGLang · TA", "SGLang · global", "vLLM · TA", "vLLM · global"],
   rows=["Engine generation tok/s steady (window)", "TA / global (engine steady)", "Sessions ended / finished (of 512)", "Time to 512 trajectories · finished among them",
         "Model tok/s (512-trajectory rule)", "Mean session duration", "Engine KV usage / prefix hit / mean running", "Sessions dispatching subagents · dispatches",
         "Finished rate: with subagents / without", "Router peak programs"],
   cap="CC 256, default prompt, one pair of arms per engine; the vLLM columns are the 256 row of the table above",
   setup=("Same harness, data, model, prompt and roughly 60 GiB of KV per GPU; only the inference engine changes: the SGLang image is sglang 0.5.19 / torch 2.13 + cu130 (the vLLM image is vLLM 0.24.0 / torch 2.11), "
          "both arms use the flashinfer attention backend, mem_fraction_static 0.78, max_running_requests 256, TP 4 × 2 engines. The TA arm's engines are hosted by the dynamo.sglang worker, the global arm's by verl's native sglang server, same sglang build. "
          "SGLang was run at CC 256 only. The y metric is the one used above: generation tok/s from the engine scheduler's stats (SGLang reports an interval mean every 40 decode steps), steady = median of 10-minute buckets."),
   pending=("The global arm is being re-run: the first run (10-18 11:18–13:22) completed 508 / 512 sessions (512 trajectories in 3925 s, 246 finished, 319 tok/s by the trainer's rule) but verl's native sglang server starts with <code>log_level=error</code> and left no engine stats, so it cannot enter the table; "
            "it restarted at 13:36 with <code>engine_kwargs.sglang.log_level=info</code>, result expected around 15:45. The first run is kept under <code>runs/global-h20sgcc256-10160955-nostats</code>."),
   result=("On SGLang the TA / global ratio of engine steady state is <strong>{ratio:.2f}×</strong> ({ta_v:,} vs {gl_v:,}); on vLLM it is {vratio:.2f}× ({vta_v:,} vs {vgl_v:,}). The whole difference sits in the global arm: on vLLM it runs CC 256 at KV {vgl_kv}%, prefix hit {vgl_hit}%, mean running {vgl_run}; "
           "on SGLang at KV {gl_kv}%, hit {gl_hit}%, running {gl_run}. TA keeps the engines at KV {ta_kv}%, hit {ta_hit}%, running {ta_run} on both. "
           "By the trainer's rule, TA on SGLang collects 512 trajectories in {ta_w:.0f} s against {gl_w:.0f} s for global ({dw:+.0%}), with {ta_f} vs {gl_f} finished among them; sessions that dispatched subagents finish at {ta_fw:.0%} vs {gl_fw:.0%}. "
           "Conclusion: the size of TA's engine-side gain depends on how the engine behaves without admission control. The 4× on vLLM 0.24 comes from the global arm's saturated-KV state on this machine; on sglang 0.5.19 the same load does not put global into that state, and TA's gain narrows to {ratio:.2f}× in engine throughput and {dwabs:.0%} in time to 512 trajectories."),
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

def section(lang, A):
    t = TXT[lang]; sg_ta, sg_gl, v_ta, v_gl = A["sg_ta"], A["sg_gl"], A["v_ta"], A["v_gl"]
    if sg_ta and sg_gl:
        gl_w = sg_gl["t"]["wall"]; ta_w = sg_ta["t"]["wall"]
        txt = t["result"].format(ratio=sg_ta["p"]["v"] / sg_gl["p"]["v"], ta_v=sg_ta["p"]["v"], gl_v=sg_gl["p"]["v"], vratio=v_ta["p"]["v"] / v_gl["p"]["v"], vta_v=v_ta["p"]["v"], vgl_v=v_gl["p"]["v"],
                                 vgl_kv=v_gl["e"]["kv"], vgl_hit=v_gl["e"]["hit"], vgl_run=v_gl["e"]["running"], gl_kv=sg_gl["e"]["kv"], gl_hit=sg_gl["e"]["hit"], gl_run=sg_gl["e"]["running"],
                                 ta_kv=rng(sg_ta["e"]["kv"], v_ta["e"]["kv"]), ta_hit=rng(sg_ta["e"]["hit"], v_ta["e"]["hit"]), ta_run=rng(sg_ta["e"]["running"], v_ta["e"]["running"]),
                                 ta_w=ta_w, gl_w=gl_w, dw=(ta_w - gl_w) / gl_w, dwabs=(gl_w - ta_w) / gl_w, ta_f=sg_ta["t"]["finished"], gl_f=sg_gl["t"]["finished"],
                                 ta_fw=sg_ta["sp"]["with_subagents"]["finished_rate"], gl_fw=sg_gl["sp"]["with_subagents"]["finished_rate"])
    else:
        txt = t["pending"]
    return f'<!-- sglang-table -->\n<h3>{t["h3"]}</h3>\n<p>{t["setup"]}</p>\n{table(lang, A)}\n<p>{txt}</p>\n<!-- /sglang-table -->'

def splice(html, blk):
    a, b = html.index("<!-- sglang-table -->"), html.index("<!-- /sglang-table -->") + len("<!-- /sglang-table -->")
    return html[:a] + blk + html[b:]

A = dict(sg_ta=arm("sglang", "ta-native"), sg_gl=arm("sglang", "global"), v_ta=arm("default", "ta-native"), v_gl=arm("default", "global"))
for path, lang in zip(sys.argv[1:3], ("zh", "en")):
    h = open(path).read(); h = splice(h, section(lang, A)); open(path, "w").write(h)
print("sglang section:", {k: (v["p"]["run"] if v else None) for k, v in A.items()})
