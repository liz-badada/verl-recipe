"""Synthetic Claude Code subagent trees through the uni-agent Gateway (recipe adapter).

Same tree shape as bench/subagent_load.py, but every turn goes to the gateway session
endpoint with Claude Code identity headers, so program naming, parent links and the
release of a returned subagent are done by the recipe's real code path, not emulated.
Intermediate turns set ignore_eos (finish_reason=length, like a tool_calls turn);
only a subagent's last turn may end with stop, which is what triggers its release.
"""
import argparse, asyncio, json, random, statistics, time
import aiohttp

WORD = ["alpha", "beta", "gamma", "delta", "tool", "file", "edit", "grep", "read", "bash", "test", "patch"]


def text(n_tokens, seed):
    rnd = random.Random(seed)
    return " ".join(rnd.choice(WORD) for _ in range(n_tokens))


SHAPE = {"root_sys": 1500, "sub_sys": 1200, "task": 200, "tool": 300, "max_tokens": 48, "root_turns": 1}
TOOL_GAP_S = 0.0
ROOT_SYS = SUB_SYS = ""


async def tool_gap(seed):
    if TOOL_GAP_S > 0:
        await asyncio.sleep(random.Random(seed).uniform(0.5 * TOOL_GAP_S, 1.5 * TOOL_GAP_S))


async def turn(http, gw, model, root, sid, final, messages, max_tokens, stats):
    headers = {"Content-Type": "application/json", "x-claude-code-session-id": root}
    if sid != root:
        headers["x-claude-code-agent-id"] = sid
    body = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if not final:
        body["ignore_eos"] = True
    t0 = time.monotonic()
    usage, content, finish = {}, "", None
    try:
        async with http.post(f"{gw}/sessions/{root}/v1/chat/completions", json=body, headers=headers) as r:
            raw, status = await r.text(), r.status
            if status == 200:
                data = json.loads(raw)
                usage = data.get("usage") or {}
                choice = (data.get("choices") or [{}])[0]
                content = (choice.get("message") or {}).get("content") or ""
                finish = choice.get("finish_reason")
            else:
                stats["bodies"].append(raw[:300])
    except asyncio.TimeoutError:
        status = "timeout"
    dt = time.monotonic() - t0
    stats["turns"].append({"session": sid, "parent": None if sid == root else root, "final": final, "status": status,
                           "finish_reason": finish, "latency_s": dt,
                           "prompt_tokens": usage.get("prompt_tokens", 0), "completion_tokens": usage.get("completion_tokens", 0)})
    if status != 200:
        stats["errors"] += 1
    return content


async def subagent(http, gw, model, root, idx, turns, stats):
    sid = f"{root}-sub{idx}"
    msgs = [{"role": "system", "content": SUB_SYS}, {"role": "user", "content": "Task: " + text(SHAPE["task"], f"{sid}-task")}]
    for t in range(turns):
        content = await turn(http, gw, model, root, sid, t + 1 == turns, msgs, SHAPE["max_tokens"], stats)
        if t + 1 < turns:
            await tool_gap(f"{sid}-g{t}")
            msgs = msgs + [{"role": "assistant", "content": content or text(40, f"{sid}-a{t}")},
                           {"role": "user", "content": "Tool result: " + text(SHAPE["tool"], f"{sid}-r{t}")}]


async def control(http, method, url):
    async with http.request(method, url) as r:
        return r.status, await r.text()


async def tree(http, gw, model, root, subagents, turns, stats):
    t0 = time.monotonic()
    errors_before = stats["errors"]
    status, body = await control(http, "POST", f"{gw}/control/sessions/{root}")
    if status != 200:
        stats["errors"] += 1
        stats["bodies"].append(f"create {status} {body[:200]}")
        return
    msgs = [{"role": "system", "content": ROOT_SYS}, {"role": "user", "content": "Fix the failing test in " + text(100, f"{root}-task")}]
    content = await turn(http, gw, model, root, root, False, msgs, SHAPE["max_tokens"], stats)
    await asyncio.gather(*(subagent(http, gw, model, root, i, turns, stats) for i in range(subagents)))
    for t in range(SHAPE["root_turns"]):
        msgs = msgs + [{"role": "assistant", "content": content or text(40, f"{root}-a{t}")},
                       {"role": "user", "content": "Subagent reports: " + text(SHAPE["tool"], f"{root}-r{t}")}]
        content = await turn(http, gw, model, root, root, t + 1 == SHAPE["root_turns"], msgs, SHAPE["max_tokens"], stats)
        await tool_gap(f"{root}-g{t}")
    tc = time.monotonic()
    status, body = await control(http, "DELETE", f"{gw}/control/sessions/{root}")
    close_s = time.monotonic() - tc
    if status != 200:
        stats["errors"] += 1
        stats["bodies"].append(f"close {status} {body[:200]}")
    stats["sessions"].append({"session": root, "latency_s": time.monotonic() - t0, "close_s": close_s, "ok": errors_before == stats["errors"]})


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gateway", default="http://127.0.0.1:8900")
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
    a = ap.parse_args()
    global ROOT_SYS, SUB_SYS, TOOL_GAP_S
    SHAPE.update({key: getattr(a, key) for key in SHAPE})
    TOOL_GAP_S = a.tool_gap_s
    ROOT_SYS = "You are the main coding agent. " + text(SHAPE["root_sys"], "root-system")
    SUB_SYS = "You are an Explore subagent. " + text(SHAPE["sub_sys"], "sub-system")
    stats = {"turns": [], "sessions": [], "errors": 0, "bodies": []}
    sem = asyncio.Semaphore(a.concurrency)

    async def limited(i):
        async with sem:
            await tree(http, a.gateway, a.model, f"root-{i:03d}", a.subagents, a.turns, stats)

    t0 = time.monotonic()
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=0), timeout=aiohttp.ClientTimeout(total=a.request_timeout)) as http:
        await asyncio.gather(*(limited(i) for i in range(a.sessions)))
        wall = time.monotonic() - t0
        try:
            async with http.get(f"{a.gateway}/control/stats") as r:
                gateway = json.loads(await r.text())
        except Exception as e:  # noqa: BLE001
            gateway = {"error": str(e)}
    lat = sorted(s["latency_s"] for s in stats["sessions"]) or [0.0]
    tl = sorted(t["latency_s"] for t in stats["turns"]) or [0.0]
    completion = sum(t["completion_tokens"] for t in stats["turns"])
    finish = {}
    for t in stats["turns"]:
        finish[str(t["finish_reason"])] = finish.get(str(t["finish_reason"]), 0) + 1
    summary = {
        "driver": "gateway", "sessions": a.sessions, "subagents": a.subagents, "turns": a.turns, "concurrency": a.concurrency,
        "shape": dict(SHAPE), "tool_gap_s": TOOL_GAP_S, "release_returned_subagents": "gateway",
        "wall_s": wall, "errors": stats["errors"], "requests": len(stats["turns"]),
        "completion_tokens": completion, "prompt_tokens": sum(t["prompt_tokens"] for t in stats["turns"]),
        "completion_tokens_per_s": completion / wall if wall else 0,
        "completed_sessions": sum(1 for s in stats["sessions"] if s["ok"]),
        "session_latency_mean_s": statistics.mean(lat), "session_latency_p95_s": lat[int(0.95 * (len(lat) - 1))],
        "session_close_mean_s": statistics.mean([s["close_s"] for s in stats["sessions"]] or [0.0]),
        "turn_latency_mean_s": statistics.mean(tl), "turn_latency_p95_s": tl[int(0.95 * (len(tl) - 1))],
        "finish_reasons": finish, "gateway": gateway,
    }
    json.dump({"summary": summary, **stats}, open(a.out, "w"))
    print(json.dumps(summary))


asyncio.run(main())
