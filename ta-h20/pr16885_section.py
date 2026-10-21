"""pr16885_section.py <zh.html> <en.html>: the effect of Dynamo PR #16885 (reclaim idle ThunderAgent reservations on
demand) on the TA arms, as a subsection of section 三/3 spliced between <!-- pr16885 --> and <!-- /pr16885 -->.

Reads regime_points.json["pr16885"][engine]["ta-native"] and pairs every point with the unpatched TA arm and the global
arm at the same CC from regime_points["default"] (vLLM) or ["sglang"]. Per run: engine_rate.py's columns, time to 512
trajectories (time_to_512 rule), and from the frontend log the reclaim events, forced program resumes and the peak
paused_programs. CCs whose patched arm has not landed are listed as running.
"""
import json, os, re, subprocess, sys

H = os.path.dirname(os.path.abspath(__file__))
P = json.load(open(f"{H}/regime_points.json"))
ENGINES = (("vllm", "default", "vLLM 0.24"), ("sglang", "sglang", "SGLang 0.5.19"))
CCS = (256, 384, 512)

def pt(regime, series, cc): return next((d for d in P.get(regime, {}).get(series, []) if d["cc"] == cc), None)

def engine(run):
    line = subprocess.run([sys.executable, f"{H}/engine_rate.py", f"{H}/runs/{run}"], capture_output=True, text=True).stdout.strip().split("\n")[-1]
    f = line.split()
    return dict(steady=int(f[4]), prefill=float(f[5]), kv=int(f[6]), hit=int(f[7]), running=int(f[8]))

def to512(run):
    d = json.load(open(f"{H}/runs/{run}/summary.json"))
    rows = [r for r in d.get("sessions_all", d["sessions"]) if r.get("start")]
    t0 = min(r["start"] for r in rows)
    first = sorted((r for r in rows if r.get("done") and r.get("end")), key=lambda r: r["end"])[:512]
    return first[-1]["end"] - t0 if len(first) == 512 else None

def router(run):
    """Counts from the frontend log: reclaim events (#16885 only), forced program resumes, peak paused_programs."""
    try: txt = open(f"{H}/runs/{run}/dynamo/verl_dynamo_replica0_frontend.log", errors="replace").read()
    except FileNotFoundError: return dict(reclaims=0, forced=0, paused=0)
    paused = [int(x) for x in re.findall(r"paused_programs=(\d+)", txt)]
    return dict(reclaims=txt.count("Reclaimed idle reservations"), forced=len(re.findall(r"forced[a-z ]*resum", txt, re.I)), paused=max(paused) if paused else 0)

def arm(regime, series, cc):
    p = pt(regime, series, cc)
    if not p: return None
    return dict(p=p, e=engine(p["run"]), t=to512(p["run"]), r=router(p["run"]))

def rows():
    out = []
    for key, base, label in ENGINES:
        for cc in CCS:
            fxp = next((d for d in P.get("pr16885", {}).get(key, {}).get("ta-native", []) if d["cc"] == cc), None)
            fx = dict(p=fxp, e=engine(fxp["run"]), t=to512(fxp["run"]), r=router(fxp["run"])) if fxp else None
            out.append((label, cc, fx, arm(base, "ta-native", cc), arm(base, "global", cc)))
    return out

TXT = {
 "zh": dict(h3="同事的 Dynamo 修复 #16885 在这台机器上的效果", running="运行中",
   cols=["引擎 · CC", "TA + #16885 稳态", "TA 稳态（本页）", "global 稳态", "#16885 / TA", "#16885 / global", "收齐 512 条用时 #16885 / TA", "KV / 命中 / running：#16885 ‖ TA", "reclaim 次数", "强制 resume #16885 / TA", "paused 峰值 #16885 / TA"],
   cap="只跑 TA 臂（global 臂不经过 TA 插件）；镜像、KV 上限、数据、prompt 与本页其它 TA 臂相同，只换 router 插件的 wheel",
   setup=("同事在 Dynamo 上提了 <a href=\"https://github.com/ai-dynamo/dynamo/pull/16885\">PR #16885</a>（router 插件 <code>scheduler.rs</code>，+437 / −7）：当有模型调用在等容量时，回收最老的空闲 Acting 程序的预留；resume 和 backlog 判断只数真正在等的请求。"
          "这和本页第三节观察到的现象是同一个根因：TA 把每个程序按整段最近一轮上下文记账，空闲的 Acting 程序占着账面容量，别人进不来。我们把这个 PR 摘到三个基准镜像共用的 nightly（dev20260924）上重新打了 wheel："
          "补丁本身能干净应用，但它的 hard-pin 感知依赖 nightly 里还没有的 #15290，去掉了那一个元素和两个 pin 测试，其余 74 个单元测试通过；镜像里 <code>pip freeze</code> 只差这一行。然后在 vLLM 0.24 和 SGLang 两个镜像上各跑 TA 的 256 / 512 / 384 三档，和本页已有的 TA、global 臂同口径对照。"),
   result=("<strong>结果是修复版在这台机器上更慢</strong>：vLLM 上三档稳态掉 {v_lo}–{v_hi}%，SGLang 上掉 {s_lo}–{s_hi}%，收齐 512 条轨迹的时间多出 {w_lo}–{w_hi}%。补丁确实在工作（每臂 {rc_lo:,}–{rc_hi:,} 次 reclaim），放进引擎的程序数翻倍（running {run_fx} 对 {run_ta}），引擎 KV 占用从 {kv_ta}% 升到 {kv_fx}%，但 prefix 命中从 {hit_ta}% 掉到 {hit_fx}%，prefill 量翻倍。H20 的算力弱，这部分重算直接从 decode 时间里扣掉，没有 preemption，所以不是 global 臂那种崩法，是另一种代价。"
           "强制 resume 和 paused 峰值与未修复几乎一样，说明暂停不是只由空闲 Acting 的预留造成的：按整段上下文记账的预留在真实 KV 只有一半时就顶到 0.85 的 resume 上限，回收只是让程序在 Acting 和排队之间多转几圈。"
           "同事在 H100 上报告修复后 global 并发 512 下 TA 为 vLLM 基线的 1.75×；H100 算得起翻倍的 prefill，放更多程序进引擎可能是赚的，H20 算不起。这正是第七节那条「倍数取决于硬件上基线和 TA 各自的代价」的另一半。#16885 尚未合入 Dynamo，本页 PR 不依赖它；这组数据只说明在 H20 上不应把它当作默认开启。"),
   pending="SGLang 的 CC 384 臂还在跑，出来后补进表里。"),
 "en": dict(h3="What a colleague's Dynamo fix #16885 does on this machine", running="running",
   cols=["Engine · CC", "TA + #16885 steady", "TA steady (this page)", "global steady", "#16885 / TA", "#16885 / global", "Time to 512 trajectories #16885 / TA", "KV / hit / running: #16885 ‖ TA", "Reclaim events", "Forced resumes #16885 / TA", "Peak paused #16885 / TA"],
   cap="TA arms only (the global arm never passes through the TA plugin); image, KV cap, data and prompt as the other TA arms on this page, only the router plugin wheel differs",
   setup=("A colleague opened <a href=\"https://github.com/ai-dynamo/dynamo/pull/16885\">PR #16885</a> on Dynamo (router plugin <code>scheduler.rs</code>, +437 / −7): when model calls are waiting for capacity, reclaim the reservations of the oldest idle Acting programs; resume and backlog checks count only live waiting requests. "
          "It addresses the same root cause this page's section 3 observes: TA charges every program for its whole last-turn context, so idle Acting programs hold capacity on paper and nothing else gets in. We rebuilt the wheel with that PR cherry-picked onto the nightly the three benchmark images share (dev20260924): "
          "the patch applies cleanly, but its hard-pin awareness depends on #15290, which that nightly lacks, so that one element and two pin tests were dropped; the other 74 unit tests pass and <code>pip freeze</code> in the images differs by this one line. TA then ran CC 256 / 512 / 384 on the vLLM 0.24 image and on the SGLang image, compared like for like with the TA and global arms already on this page."),
   result=("<strong>The patched build is slower on this machine</strong>: steady state drops {v_lo}–{v_hi}% at the three CCs on vLLM and {s_lo}–{s_hi}% on SGLang, and the time to 512 trajectories grows {w_lo}–{w_hi}%. The patch is active ({rc_lo:,}–{rc_hi:,} reclaim events per arm) and the number of programs inside the engine doubles (running {run_fx} vs {run_ta}); engine KV rises from {kv_ta}% to {kv_fx}%, but the prefix hit rate falls from {hit_ta}% to {hit_fx}% and prefill volume doubles. On the compute-weak H20 that recompute comes straight out of decode time; there is no preemption, so this is not the global arm's collapse but a different cost. "
           "Forced resumes and peak paused programs are unchanged, which says the pauses are not caused by idle Acting reservations alone: reservations charged at full context hit the 0.85 resume ceiling while real KV is at half, and reclaiming only cycles programs between Acting and the queue. "
           "The colleague reports 1.75× over the vLLM baseline at global concurrency 512 on H100 with the fix; an H100 can afford the doubled prefill, so admitting more programs may pay there, and an H20 cannot. That is the other half of section 7's point that the multiple depends on what the baseline and TA each pay on the hardware. #16885 is not merged in Dynamo and this page's PR does not depend on it; these runs only say it should not be on by default on H20."),
   pending="The SGLang CC 384 arm is still running and joins the table when it lands."),
}

def table(lang, R):
    t = TXT[lang]; run = t["running"]
    def rate(a): return f'{a["p"]["v"]:,} ({a["p"]["w"]:,})' if a else run
    def ratio(a, b): return f'<strong>{a["p"]["v"] / b["p"]["v"]:.2f}×</strong>' if a and b else run
    def w(a): return (f'{a["t"]:.0f} s' if a["t"] else "—") if a else run
    def e(a): return f'{a["e"]["kv"]}% / {a["e"]["hit"]}% / {a["e"]["running"]}' if a else run
    body = ""
    for label, cc, fx, ta, gl in R:
        if not ta or not gl: continue
        body += (f'<tr><td>{label} · {cc}</td><td class="num">{rate(fx)}</td><td class="num">{rate(ta)}</td><td class="num">{rate(gl)}</td>'
                 f'<td class="num">{ratio(fx, ta)}</td><td class="num">{ratio(fx, gl)}</td><td class="num">{w(fx)} / {w(ta)}</td><td class="num">{e(fx)} ‖ {e(ta)}</td>'
                 f'<td class="num">{fx["r"]["reclaims"]:,}</td><td class="num">{fx["r"]["forced"]} / {ta["r"]["forced"]}</td><td class="num">{fx["r"]["paused"]} / {ta["r"]["paused"]}</td></tr>'
                 if fx else
                 f'<tr><td>{label} · {cc}</td><td class="num">{run}</td><td class="num">{rate(ta)}</td><td class="num">{rate(gl)}</td>' + f'<td class="num">{run}</td>' * 7 + '</tr>')
    head = "".join(f'<th{" class=num" if i else ""}>{c}</th>' for i, c in enumerate(t["cols"]))
    return f'<div class="scroller"><table><caption>{t["cap"]}</caption><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'

def summary(lang, R):
    t = TXT[lang]
    done = [(label, fx, ta) for label, cc, fx, ta, gl in R if fx and ta]
    if not done: return t["pending"]
    def pct(xs): xs = sorted(xs); return (f"{xs[0]:.0f}", f"{xs[-1]:.0f}")
    v = [(1 - fx["p"]["v"] / ta["p"]["v"]) * 100 for label, fx, ta in done if label.startswith("vLLM")]
    s = [(1 - fx["p"]["v"] / ta["p"]["v"]) * 100 for label, fx, ta in done if label.startswith("SGLang")]
    w = [(fx["t"] / ta["t"] - 1) * 100 for label, fx, ta in done if fx["t"] and ta["t"]]
    rc = sorted(fx["r"]["reclaims"] for _, fx, _ in done)
    def avg(k, which): return round(sum(x[k] for x in which) / len(which))
    fxe = [fx["e"] for _, fx, _ in done]; tae = [ta["e"] for _, _, ta in done]
    txt = t["result"].format(v_lo=pct(v)[0] if v else "—", v_hi=pct(v)[1] if v else "—", s_lo=pct(s)[0] if s else "—", s_hi=pct(s)[1] if s else "—",
                             w_lo=pct(w)[0], w_hi=pct(w)[1], rc_lo=rc[0], rc_hi=rc[-1], run_fx=avg("running", fxe), run_ta=avg("running", tae),
                             kv_fx=avg("kv", fxe), kv_ta=avg("kv", tae), hit_fx=avg("hit", fxe), hit_ta=avg("hit", tae))
    if any(fx is None for _, _, fx, ta, _ in R if ta): txt += " " + t["pending"]
    return txt

def section(lang, R):
    t = TXT[lang]
    return f'<!-- pr16885 -->\n<h3>{t["h3"]}</h3>\n<p>{t["setup"]}</p>\n{table(lang, R)}\n<p>{summary(lang, R)}</p>\n<!-- /pr16885 -->'

def splice(html, blk):
    a, b = html.index("<!-- pr16885 -->"), html.index("<!-- /pr16885 -->") + len("<!-- /pr16885 -->")
    return html[:a] + blk + html[b:]

R = rows()
for path, lang in zip(sys.argv[1:3], ("zh", "en")):
    html = open(path).read()
    if "<!-- pr16885 -->" not in html:
        html = html.replace("<!-- /sglang-table -->", "<!-- /sglang-table -->\n<!-- pr16885 --><!-- /pr16885 -->", 1)
    open(path, "w").write(splice(html, section(lang, R)))
print("pr16885 section:", [(label, cc, bool(fx)) for label, cc, fx, ta, gl in R])
