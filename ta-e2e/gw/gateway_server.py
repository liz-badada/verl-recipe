"""Standalone uni-agent Gateway running the verl-recipe ThunderAgent adapter, no Ray.

The recipe's `_DynamoGatewayActor` is served as a plain process. Its backend is a thin
client that reaches a Dynamo frontend the way the recipe's TA HTTP server does: token-id
prompt on /v1/completions, `x-dynamo-session-id` = program, `x-dynamo-parent-session-id`
= parent, a session-final request on finalize_program. So the gateway's real program
tree, per-program serialization and release-on-return run end-to-end against GPUs.
Control routes create and close sessions and expose counters for the load driver.
"""
import argparse
import asyncio
import json
import logging
import time
import uuid

import aiohttp
import ray.util
import uvicorn
from transformers import AutoTokenizer

from uni_agent.gateway.config import GatewayActorConfig
from verl.workers.rollout.replica import TokenOutput
from recipe.dynamo.uniagent_gateway import _DynamoGatewayActor

log = logging.getLogger("gateway_e2e")


class FrontendBackend:
    _auto_finalize = False

    def __init__(self, url, model, tokenizer, timeout_s):
        self.url, self.model, self.tok, self.timeout_s = url, model, tokenizer, timeout_s
        self.stats = {"generate": 0, "generate_errors": 0, "finalize": 0, "finalize_errors": 0,
                      "completion_tokens": 0, "finish_reasons": {}, "finalized_programs": []}
        self._http = None

    async def _post(self, payload, session_id, parent=None, final=False):
        if self._http is None:
            self._http = aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=0),
                                               timeout=aiohttp.ClientTimeout(total=self.timeout_s))
        headers = {"x-dynamo-session-id": session_id, "X-Request-Id": f"{session_id}-{uuid.uuid4().hex}"}
        if parent:
            headers["x-dynamo-parent-session-id"] = parent
        if final:
            headers["x-dynamo-session-final"] = "true"
        async with self._http.post(self.url, json=payload, headers=headers) as r:
            return r.status, await r.text()

    async def generate(self, request_id, *, prompt_ids, sampling_params, program_id=None, parent_program_id=None, **_):
        sid = str(program_id or request_id)
        sp = dict(sampling_params)
        for key in ("logprobs", "prompt_logprobs"):
            sp.pop(key, None)
        max_tokens = sp.pop("max_tokens", None) or sp.pop("max_new_tokens", None) or 128
        payload = {"model": self.model, "prompt": [int(t) for t in prompt_ids], "max_tokens": int(max_tokens), "stream": False}
        payload.update({k: v for k, v in sp.items() if v is not None})
        self.stats["generate"] += 1
        status, body = await self._post(payload, sid, parent_program_id)
        if status != 200:
            self.stats["generate_errors"] += 1
            raise RuntimeError(f"frontend status={status} body={body[:300]!r}")
        data = json.loads(body)
        choice = data["choices"][0]
        finish = choice.get("finish_reason") or "stop"
        self.stats["finish_reasons"][finish] = self.stats["finish_reasons"].get(finish, 0) + 1
        self.stats["completion_tokens"] += (data.get("usage") or {}).get("completion_tokens", 0)
        ids = self.tok.encode(choice.get("text") or "", add_special_tokens=False) or [self.tok.eos_token_id]
        return TokenOutput(token_ids=ids, stop_reason=finish)

    async def finalize_program(self, session_id, routing_key=None):
        self.stats["finalize"] += 1
        payload = {"model": self.model, "prompt": [self.tok.eos_token_id], "max_tokens": 1, "stream": False}
        status, body = await self._post(payload, str(session_id), final=True)
        if status != 200:
            self.stats["finalize_errors"] += 1
            raise RuntimeError(f"finalize status={status} body={body[:300]!r}")
        self.stats["finalized_programs"].append(str(session_id))


async def main(a):
    ray.util.get_node_ip_address = lambda: "127.0.0.1"
    tok = AutoTokenizer.from_pretrained(a.model)
    backend = FrontendBackend(a.frontend, a.model, tok, a.timeout)
    # ignore_eos lets the driver make intermediate turns end with finish_reason=length
    # (a stand-in for tool_calls) and only the subagent's final answer end with stop.
    config = GatewayActorConfig(tokenizer=tok, rollout_backend="vllm", allowed_request_sampling_param_keys={"ignore_eos"})
    actor = _DynamoGatewayActor(config, backend)
    actor._server_address = "127.0.0.1"
    app = actor._app

    @app.post("/control/sessions/{sid}")
    async def create(sid: str):
        await actor.create_session(sid, sampling_params={})
        return {"ok": True}

    @app.delete("/control/sessions/{sid}")
    async def close(sid: str):
        t0 = time.monotonic()
        trajectories = await actor.finalize_session(sid)
        return {"trajectories": len(trajectories), "close_s": time.monotonic() - t0}

    @app.get("/control/stats")
    async def stats():
        s = dict(backend.stats)
        s["finalized_programs"] = len(s["finalized_programs"])
        s.update(open_sessions=len(actor._sessions),
                 tracked_programs=sum(len(v) for v in actor._programs.values()),
                 pending_releases=sum(len(v) for v in actor._releases.values()))
        return s

    actor._server_port = a.port
    actor._server_base_url = f"http://127.0.0.1:{a.port}"
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=a.port, log_level="warning"))
    actor._server_task = asyncio.current_task()
    log.warning("gateway e2e serving on %s -> %s", actor._server_base_url, a.frontend)
    await server.serve()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--frontend", default="http://127.0.0.1:8801/v1/completions")
    ap.add_argument("--port", type=int, default=8900)
    ap.add_argument("--timeout", type=float, default=900.0)
    asyncio.run(main(ap.parse_args()))
