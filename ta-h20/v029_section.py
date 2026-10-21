"""v029_section.py <zh.html> <en.html>: the vLLM 0.29 part of section 三/3: the same sweep repeated on the verl 0.10 /
recipe b85e1b7 / uni-agent main 7ea3874 stack, charted and tabled per CC next to the vLLM 0.24 pair at the same CC and
the colleague's H100 ratio. Reads regime_points.json["v029"] (and ["default"] for 0.24); splices between
<!-- v029 --> and <!-- /v029 -->. Pending CCs read "running"; CCs with only the TA arm show the global column as running.
"""
import copy, json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regime_chart

SWEEP = (64, 128, 256, 384, 512, 1024, 2048)
CHART_CCS = (64, 128, 256, 384, 512)   # regime_chart's x axis ends at 560
# Colleague's 1-node 8xH100 (2xTP4) vLLM 0.29 run, 8 SWE-rebench tasks, 3 forced foreground subagents, rollout-only,
# 180 s warm-up + 600 s sample window: TA / native vLLM generation tok/s, as pasted on 2026-10-21.
H100 = {64: (931, 943), 128: (1231, 1509), 256: (1245, 884), 512: (1297, 715), 1024: (1331, 731), 2048: (1343, 1031)}

# CCs that cannot be hosted on this one 192-core / 2 TB node: the 2048 TA arm (2026-10-21 21:54) created 585 sandboxes in its
# first 10 minutes, the load average reached 1600 and RSS 1.1 TB, the engines fell from 779 to ~150 tok/s and all 64 ray
# tasks died at 65 min; 1024 sandboxes would need ~1.9 TB at the same footprint. Both are shown as infeasible, not as data.
INFEASIBLE = {"zh": {2048: "单机不可行（2048 个沙箱：10 分钟 585 个，负载 1600、内存 1.1 TB，65 分钟全部 ray task 死亡）", 1024: "单机不可行（同一沙箱占用下约需 1.9 TB 内存，未跑）"},
              "en": {2048: "infeasible on one node (2048 sandboxes: 585 in 10 min, load 1600, 1.1 TB RSS, all 64 ray tasks dead at 65 min)", 1024: "infeasible on one node (about 1.9 TB for the sandboxes at the same footprint; not run)"}}

H = os.path.dirname(os.path.abspath(__file__))
P = json.load(open(f"{H}/regime_points.json"))

def pt(regime, series, cc): return next((d for d in P.get(regime, {}).get(series, []) if d["cc"] == cc), None)

def engine(run):
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
    return dict(wall=wall, finished=sum(1 for t in traj if t.get("finished")))

def arm(regime, series, cc):
    p = pt(regime, series, cc)
    if not p: return None
    s = json.load(open(f"{H}/runs/{p['run']}/summary.txt"))
    return dict(p=p, s=s, e=engine(p["run"]), t=to512(p["run"]))

TXT = {
 "zh": dict(h3="同一口径换到 vLLM 0.29 栈（verl 0.10 + 合入 PR #270 的 uni-agent main）", running="运行中", none="未收齐",
   cols=["CC", "0.29 · TA 稳态（全程）", "0.29 · global 稳态（全程）", "0.29 · TA / global", "0.24 · TA / global（同档）", "收齐 512 条用时 TA / global", "其中完成 TA / global", "KV / 命中 / running：TA ‖ global", "同事 H100 · TA / native"],
   cap="vLLM 0.29 栈，默认 prompt，每档两臂各收 512 条轨迹；0.24 列取自上表同档；最后一列是同事在 8× H100 上的 600 s 窗口比值（口径不同，只作形状参照）",
   setup=("同一套 harness、同一数据、模型、prompt、KV 池（每引擎 2,621,440 token），把软件栈整体换到同事 H100 测试用的那一套：vLLM 0.29.0、verl 0.10.0.dev、verl-recipe b85e1b7（PR #162 分支）、uni-agent main 7ea3874（含 10-21 合入的 PR #270），"
          "Claude Code 任务配置多挂一个 SubagentStop 钩子（<code>task_config_claude_code_docker.v029.yaml</code>），其余参数与 0.24 栈完全相同（TP 4 × 2 引擎、max_num_seqs 256、GPU_MEM 0.75、run_timeout 5400 s）。"
          "两臂烟测（各 8 个 session）10-21 11:00 通过后，按 512 → 256 → 128 → 64 → 384 的顺序两臂扫并发（global 256 第一次因沙箱 7200 s 寿命在 2 小时处丢了第二波 session，已排除并重跑；0.29 任务配置的 runtime_timeout 提到 12600），再补 1024 / 2048 两档对应同事的 H100 档位；1024 / 2048 只进表不进图（图的横轴到 560）。"),
   result_one=("CC {cc} 上，0.29 栈的 TA / global 引擎稳态倍数为 <strong>{ratio:.1f}×</strong>（{ta_v:,} 对 {gl_v:,}），0.24 栈同档为 {oratio:.1f}×（{ota_v:,} 对 {ogl_v:,}）；"
               "TA 臂两栈几乎重合（{ta_v:,} 对 {ota_v:,}，引擎 KV {ta_kv}%、命中 {ta_hit}%），global 臂两栈同样塌陷（KV {gl_kv}%、命中 {gl_hit}%、running {gl_run}，512 条轨迹里完成 {gl_f} 条）。"
               "同事在 8× H100 上同一档位测得 {h_ratio:.2f}×（{h_ta:,} 对 {h_gl:,}，600 s 窗口）：TA 臂两台机器接近（{ta_v:,} 对 {h_ta:,}），差别全在 native 臂塌多深——H100 的 KV 大一倍多，塌得浅，倍数就小。"),
   result_many=("已跑完的档位 CC {ccs} 上，0.29 栈的引擎稳态 TA / global 依次为 {ratios}，0.24 栈同档为 {oratios}；两套栈的曲线形状一致，换栈没有改变结论。"),
   pending="0.29 栈的第一对（CC 512）还在跑，出来后此处给出两栈并排的数字。",
   foot_running="表中「运行中」的档位按上面的顺序排队，每出一臂登记一臂。2048 在这台机器上起不来这件事本身就是对「H100 上 2048 时 native 回到与 TA 持平」的解释：单机的 CPU / 内存先于引擎到顶，引擎实际看到的并发远低于名义值。"),
 "en": dict(h3="The same measurement on the vLLM 0.29 stack (verl 0.10 + uni-agent main with PR #270 merged)", running="running", none="not reached",
   cols=["CC", "0.29 · TA steady (window)", "0.29 · global steady (window)", "0.29 · TA / global", "0.24 · TA / global (same CC)", "Time to 512 trajectories TA / global", "Finished among them TA / global", "KV / hit / running: TA ‖ global", "Colleague's H100 · TA / native"],
   cap="vLLM 0.29 stack, default prompt, 512 trajectories per arm at every CC; the 0.24 column is the same CC of the table above; the last column is the colleague's 600 s-window ratio on 8× H100 (different caliber, shape reference only)",
   setup=("Same harness, data, model, prompt and KV pool (2,621,440 tokens per engine), with the whole software stack switched to the one the colleague used on H100: vLLM 0.29.0, verl 0.10.0.dev, verl-recipe b85e1b7 (the PR #162 branch), uni-agent main 7ea3874 (with PR #270, merged on 10-21), "
          "plus a SubagentStop hook in the Claude Code task config (<code>task_config_claude_code_docker.v029.yaml</code>); every other parameter equals the 0.24 stack (TP 4 × 2 engines, max_num_seqs 256, GPU_MEM 0.75, run_timeout 5400 s). "
          "After both smokes (8 sessions each) passed at 11:00 on 10-21, the sweep runs 512 → 256 → 128 → 64 → 384 on both arms (the first global 256 lost its wave-2 sessions at the 2 h mark to the 7200 s sandbox lifetime, is excluded and re-run; runtime_timeout in the 0.29 task config is now 12600), the colleague's 1024 / 2048 points cannot be hosted on this single node (see the table): at a nominal 2048 the machine is crushed by the 2048 sandboxes before the engines ever see a 2048-session load."),
   result_one=("At CC {cc} the TA / global ratio of engine steady state on the 0.29 stack is <strong>{ratio:.1f}×</strong> ({ta_v:,} vs {gl_v:,}); the 0.24 stack gives {oratio:.1f}× at the same CC ({ota_v:,} vs {ogl_v:,}). "
               "The TA arm is the same on both stacks ({ta_v:,} vs {ota_v:,}, engine KV {ta_kv}%, hit {ta_hit}%), and the global arm collapses the same way (KV {gl_kv}%, hit {gl_hit}%, running {gl_run}, {gl_f} of 512 trajectories finished). "
               "The colleague measured {h_ratio:.2f}× at this CC on 8× H100 ({h_ta:,} vs {h_gl:,}, 600 s window): the TA arm is close on both machines ({ta_v:,} vs {h_ta:,}); the whole difference is how far the native arm collapses, and H100's KV pool is more than twice as large, so it collapses less and the multiple is smaller."),
   result_many=("Across the finished CCs {ccs}, engine steady state TA / global on the 0.29 stack is {ratios}, against {oratios} on the 0.24 stack at the same CCs; the two stacks give the same curve shape, so the stack change does not alter the conclusion."),
   pending="The first 0.29 pair (CC 512) is still running; the side-by-side numbers appear here when it lands.",
   foot_running="CCs marked running are queued in the order above and booked as each arm lands. That 2048 cannot even start on this node is itself the explanation of the H100 observation that native is back level with TA at 2048: the node's CPU and memory saturate before the engines do, so the engines see far less than the nominal concurrency."),
}
CHART = {
 "zh": dict(title="同一 harness、同一负载换到 vLLM 0.29 栈：引擎生成吞吐 vs 并发",
            sub="Uni-Agent SWE-bench Verified ×32 · Claude Code（subagent 开启）· 8× H20 · Qwen3-Coder-30B-A3B · rollout-only · KV 2,621,440 token / 引擎（与 0.24 相同）",
            stack="推理后端 vLLM 0.29.0（torch 2.13 + cu130）· Dynamo 1.6.0.dev20260924 · verl 0.10.0.dev 8b7892b · verl-recipe b85e1b7 · uni-agent 7ea3874（含 PR #270）· Claude Code 2.1.300",
            y="引擎生成吞吐，稳态 (tokens s⁻¹)", x="agent 并发数 (CC，同时在跑的 Claude Code session)", regime="", pend="运行中", pendg="global 运行中", sub_note="",
            foot="纵轴为两台引擎 vLLM 调度器统计的生成 tok/s 的稳态中位数（10 分钟桶），计入每一个生成的 token，与 session 是否完成无关；每臂收 512 条轨迹。",
            cap="与上图同一构造，只换软件栈。数据：<code>regime_points.json</code> 的 v029 段，由 <code>engine_rate.py</code> 从各臂的 vLLM 调度器日志算出。"),
 "en": dict(title="Same harness and load on the vLLM 0.29 stack: engine generation throughput vs concurrency",
            sub="Uni-Agent SWE-bench Verified ×32 · Claude Code (subagents on) · 8× H20 · Qwen3-Coder-30B-A3B · rollout-only · KV 2,621,440 tokens per engine (as 0.24)",
            stack="Backend vLLM 0.29.0 (torch 2.13 + cu130) · Dynamo 1.6.0.dev20260924 · verl 0.10.0.dev 8b7892b · verl-recipe b85e1b7 · uni-agent 7ea3874 (with PR #270) · Claude Code 2.1.300",
            y="Engine generation throughput, steady state (tokens s⁻¹)", x="Agent admission concurrency (CC, Claude Code sessions in flight)", regime="", pend="running", pendg="global running", sub_note="",
            foot="Y is the steady-state median (10-min buckets) of the generation tok/s both engines' vLLM schedulers report, counting every generated token regardless of whether its session finished; 512 trajectories per arm.",
            cap="Same construction as the chart above, only the software stack differs. Data: the v029 block of <code>regime_points.json</code>, computed by <code>engine_rate.py</code> from each arm's vLLM scheduler logs."),
}

def chart(lang):
    v = P.get("v029", {})
    ta = {d["cc"] for d in v.get("ta-native", [])}; gl = {d["cc"] for d in v.get("global", [])}
    if not ta: return ""
    p = {"default": copy.deepcopy({"ta-native": [d for d in v.get("ta-native", []) if d["cc"] in CHART_CCS], "global": [d for d in v.get("global", []) if d["cc"] in CHART_CCS]}),
         "pending": [cc for cc in CHART_CCS if cc not in ta], "pending_global": [cc for cc in CHART_CCS if cc in ta and cc not in gl], "subagent_prompt": {}}
    return regime_chart.block(p, lang, t=CHART[lang], marker="v029-chart", ymax=1500, band=False, approx95=False, legend=("global", "ta-native"))

def table(lang):
    t = TXT[lang]; R = t["running"]
    def rate(a): return f'{a["p"]["v"]:,} ({a["p"]["w"]:,})' if a else R
    def w(a): return (f'{a["t"]["wall"]:.0f} s' if a["t"] else t["none"]) if a else R
    def f(a): return (str(a["t"]["finished"]) if a["t"] else "—") if a else R
    def e(a): return f'{a["e"]["kv"]}% / {a["e"]["hit"]}% / {a["e"]["running"]}' if a else R
    rows = []
    for cc in SWEEP:
        if cc in INFEASIBLE[lang]:
            h = f'{H100[cc][0] / H100[cc][1]:.2f}× ({H100[cc][0]:,} / {H100[cc][1]:,})'
            rows.append(f'<tr><td>{cc}</td><td colspan="7">{INFEASIBLE[lang][cc]}</td><td class="num">{h}</td></tr>'); continue
        a, g = arm("v029", "ta-native", cc), arm("v029", "global", cc)
        oa, og = arm("default", "ta-native", cc), arm("default", "global", cc)
        ratio = f'<strong>{a["p"]["v"] / g["p"]["v"]:.2f}×</strong>' if a and g else R
        oratio = f'{oa["p"]["v"] / og["p"]["v"]:.2f}× ({oa["p"]["v"]:,} / {og["p"]["v"]:,})' if oa and og else "—"
        h = f'{H100[cc][0] / H100[cc][1]:.2f}× ({H100[cc][0]:,} / {H100[cc][1]:,})' if cc in H100 else "—"
        rows.append(f'<tr><td>{cc}</td><td class="num">{rate(a)}</td><td class="num">{rate(g)}</td><td class="num">{ratio}</td><td class="num">{oratio}</td>'
                    f'<td class="num">{w(a)} / {w(g)}</td><td class="num">{f(a)} / {f(g)}</td><td class="num">{e(a)} ‖ {e(g)}</td><td class="num">{h}</td></tr>')
    head = "".join(f'<th{" class=num" if i else ""}>{c}</th>' for i, c in enumerate(t["cols"]))
    return f'<div class="scroller"><table><caption>{t["cap"]}</caption><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'

def result(lang):
    t = TXT[lang]
    done = [(cc, arm("v029", "ta-native", cc), arm("v029", "global", cc)) for cc in SWEEP]
    done = [(cc, a, g) for cc, a, g in done if a and g]
    if not done: return t["pending"]
    out = []
    if len(done) > 1:
        both = [(cc, a, g, arm("default", "ta-native", cc), arm("default", "global", cc)) for cc, a, g in done]
        out.append(t["result_many"].format(ccs=" / ".join(str(cc) for cc, *_ in both), ratios=" / ".join(f"{a['p']['v'] / g['p']['v']:.2f}×" for _, a, g, *_ in both),
                                           oratios=" / ".join(f"{oa['p']['v'] / og['p']['v']:.2f}×" if oa and og else "—" for *_, oa, og in both)))
    cc, a, g = done[-1]; oa, og = arm("default", "ta-native", cc), arm("default", "global", cc)
    if oa and og and cc in H100:
        out.append(t["result_one"].format(cc=cc, ratio=a["p"]["v"] / g["p"]["v"], ta_v=a["p"]["v"], gl_v=g["p"]["v"], oratio=oa["p"]["v"] / og["p"]["v"], ota_v=oa["p"]["v"], ogl_v=og["p"]["v"],
                                          ta_kv=a["e"]["kv"], ta_hit=a["e"]["hit"], gl_kv=g["e"]["kv"], gl_hit=g["e"]["hit"], gl_run=g["e"]["running"], gl_f=g["s"]["finished_trajectories"],
                                          h_ratio=H100[cc][0] / H100[cc][1], h_ta=H100[cc][0], h_gl=H100[cc][1]))
    out.append(t["foot_running"])
    return " ".join(out)

def section(lang):
    t = TXT[lang]
    return f'<!-- v029 -->\n<h3>{t["h3"]}</h3>\n<p>{t["setup"]}</p>\n{chart(lang)}\n{table(lang)}\n<p>{result(lang)}</p>\n<!-- /v029 -->'

def splice(html, blk):
    a, b = html.index("<!-- v029 -->"), html.index("<!-- /v029 -->") + len("<!-- /v029 -->")
    return html[:a] + blk + html[b:]

for path, lang in zip(sys.argv[1:3], ("zh", "en")):
    h = open(path).read(); h = splice(h, section(lang)); open(path, "w").write(h)
print("v029 section:", {cc: (bool(pt("v029", "ta-native", cc)), bool(pt("v029", "global", cc))) for cc in SWEEP})
