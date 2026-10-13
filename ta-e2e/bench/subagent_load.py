"""Synthetic Claude Code subagent trees against a Dynamo frontend.

Each session: root turn -> M subagents in parallel (T turns each, sharing one
subagent system prefix, distinct task text) -> root resumes -> root final.
Headers mirror what Dynamo's frontend derives from Claude Code identity headers.
"""
import argparse, asyncio, json, random, statistics, time
import aiohttp

WORD = ["alpha", "beta", "gamma", "delta", "tool", "file", "edit", "grep", "read", "bash", "test", "patch"]


def text(n_tokens, seed):
    rnd = random.Random(seed)
    return " ".join(rnd.choice(WORD) for _ in range(n_tokens))


SHAPE = {"root_sys": 1500, "sub_sys": 1200, "task": 200, "tool": 300, "max_tokens": 48, "root_turns": 1}
TOOL_GAP_S = 0.0  # mean think/tool time between an agent's turns; KV sits idle in HBM meanwhile
RELEASE_RETURNED = False  # what the recipe's gateway adapter does: finalize a subagent's program on its final answer
ROOT_SYS = SUB_SYS = ""


async def tool_gap(seed):
    if TOOL_GAP_S > 0:
        await asyncio.sleep(random.Random(seed).uniform(0.5 * TOOL_GAP_S, 1.5 * TOOL_GAP_S))


async def turn(session, url, model, sid, parent, final, messages, max_tokens, stats):
    headers = {"Content-Type": "application/json", "x-dynamo-session-id": sid}
    if parent:
        headers["x-dynamo-parent-session-id"] = parent
    if final:
        headers["x-dynamo-session-final"] = "true"
    t0 = time.monotonic()
    usage = {}
    try:
        async with session.post(url, json={"model": model, "messages": messages, "max_tokens": max_tokens}, headers=headers) as r:
            body, status = await r.text(), r.status
            if status == 200:
                usage = json.loads(body).get("usage") or {}
    except asyncio.TimeoutError:
        body, status = "", "timeout"
    dt = time.monotonic() - t0
    stats["turns"].append({"session": sid, "parent": parent, "final": final, "status": status, "latency_s": dt,
                           "prompt_tokens": usage.get("prompt_tokens", 0), "completion_tokens": usage.get("completion_tokens", 0)})
    if status != 200:
        stats["errors"] += 1
    return body


async def subagent(session, url, model, root, idx, turns, stats):
    sid = f"{root}-sub{idx}"
    msgs = [{"role": "system", "content": SUB_SYS}, {"role": "user", "content": "Task: " + text(SHAPE["task"], f"{sid}-task")}]
    for t in range(turns):
        await turn(session, url, model, sid, root, False, msgs, SHAPE["max_tokens"], stats)
        if t + 1 < turns:
            await tool_gap(f"{sid}-g{t}")
            msgs = msgs + [{"role": "assistant", "content": text(40, f"{sid}-a{t}")}, {"role": "user", "content": "Tool result: " + text(SHAPE["tool"], f"{sid}-r{t}")}]
    if RELEASE_RETURNED:
        await turn(session, url, model, sid, root, True, [{"role": "user", "content": "x"}], 1, stats)


async def tree(session, url, model, root, subagents, turns, stats):
    t0 = time.monotonic()
    errors_before = stats["errors"]
    msgs = [{"role": "system", "content": ROOT_SYS}, {"role": "user", "content": "Fix the failing test in " + text(100, f"{root}-task")}]
    await turn(session, url, model, root, None, False, msgs, SHAPE["max_tokens"], stats)
    await asyncio.gather(*(subagent(session, url, model, root, i, turns, stats) for i in range(subagents)))
    for t in range(SHAPE["root_turns"]):
        msgs = msgs + [{"role": "assistant", "content": text(40, f"{root}-a{t}")}, {"role": "user", "content": "Subagent reports: " + text(SHAPE["tool"], f"{root}-r{t}")}]
        await turn(session, url, model, root, None, False, msgs, SHAPE["max_tokens"], stats)
        await tool_gap(f"{root}-g{t}")
    await turn(session, url, model, root, None, True, [{"role": "user", "content": "x"}], 1, stats)
    stats["sessions"].append({"session": root, "latency_s": time.monotonic() - t0, "ok": errors_before == stats["errors"]})


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8801/v1/chat/completions")
    ap.add_argument("--model", required=True)
    ap.add_argument("--sessions", type=int, default=24)
    ap.add_argument("--subagents", type=int, default=3)
    ap.add_argument("--turns", type=int, default=3)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--out", required=True)
    ap.add_argument("--request-timeout", type=float, default=180.0)
    for key, default in SHAPE.items():
        ap.add_argument(f"--{key.replace('_', '-')}", type=int, default=default)
    ap.add_argument("--tool-gap-s", type=float, default=0.0)
    ap.add_argument("--release-returned-subagents", action="store_true")
    a = ap.parse_args()
    global ROOT_SYS, SUB_SYS, TOOL_GAP_S, RELEASE_RETURNED
    RELEASE_RETURNED = a.release_returned_subagents
    SHAPE.update({key: getattr(a, key) for key in SHAPE})
    TOOL_GAP_S = a.tool_gap_s
    ROOT_SYS = "You are the main coding agent. " + text(SHAPE["root_sys"], "root-system")
    SUB_SYS = "You are an Explore subagent. " + text(SHAPE["sub_sys"], "sub-system")
    stats = {"turns": [], "sessions": [], "errors": 0}
    sem = asyncio.Semaphore(a.concurrency)

    async def limited(i):
        async with sem:
            await tree(session, a.url, a.model, f"root-{i:03d}", a.subagents, a.turns, stats)

    t0 = time.monotonic()
    connector = aiohttp.TCPConnector(limit=0)
    async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=a.request_timeout)) as session:
        await asyncio.gather(*(limited(i) for i in range(a.sessions)))
    wall = time.monotonic() - t0
    lat = sorted(s["latency_s"] for s in stats["sessions"])
    tl = sorted(t["latency_s"] for t in stats["turns"] if not t["final"])
    completion = sum(t["completion_tokens"] for t in stats["turns"])
    prompt = sum(t["prompt_tokens"] for t in stats["turns"])
    summary = {
        "sessions": a.sessions, "subagents": a.subagents, "turns": a.turns, "concurrency": a.concurrency, "shape": dict(SHAPE), "tool_gap_s": TOOL_GAP_S, "release_returned_subagents": RELEASE_RETURNED,
        "wall_s": wall, "errors": stats["errors"], "requests": len(stats["turns"]),
        "completion_tokens": completion, "prompt_tokens": prompt, "completion_tokens_per_s": completion / wall if wall else 0,
        "completed_sessions": sum(1 for s in stats["sessions"] if s["ok"]), "session_latency_mean_s": statistics.mean(lat), "session_latency_p95_s": lat[int(0.95 * (len(lat) - 1))],
        "turn_latency_mean_s": statistics.mean(tl), "turn_latency_p95_s": tl[int(0.95 * (len(tl) - 1))],
    }
    json.dump({"summary": summary, **stats}, open(a.out, "w"))
    print(json.dumps(summary))


asyncio.run(main())
