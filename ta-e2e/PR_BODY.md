# feat(dynamo): schedule Claude Code subagents as ThunderAgent programs

## Why

In uni-agent RL rollouts every Claude Code subagent arrives at the Dynamo
frontend with a new `x-claude-code-agent-id`, so the ThunderAgent router saw
each subagent as an unrelated program: no parent link, no sibling placement,
and finished subagents stayed ACTIVE and held admission until the whole
trajectory closed. Under KV pressure the scheduler starves (a tree is only as
fast as its slowest paused child) and the throughput advantage ThunderAgent
has in the session-aware regime is lost.

## What

Recipe-only change (uni-agent and dynamo untouched), four commits:

1. `fix(dynamo)`: each frontend request gets its own `X-Request-Id`;
   `x-dynamo-session-id` stays the trajectory id.
2. `feat(dynamo)`: `dynamo/agent_identity.py` ports the frontend's Claude Code
   header precedence; `uniagent_gateway.py` reads it through a pure-ASGI
   middleware + ContextVar, maps every subagent to its own program with a
   parent link, serializes per program instead of per session, lets the
   dispatcher's next turn release its idle children and releases children
   before the root at close. `DynamoFullyAsyncLLMServerClient.generate` gains
   `program_id` / `parent_program_id` → `X-Dynamo-Parent-Session-ID`.
3. `feat(dynamo)`: `dynamo/benchmarks/thunderagent_subagent_bench.py` scores
   subagent rollouts against router metrics (program leak, pauses, prefix hit).
4. `feat(dynamo)`: release a subagent's program the moment its final answer is
   produced (`finish_reason: stop` / `stop_reason: end_turn` observed on the
   response body), so finished siblings stop holding admission.

## Tests

`pytest recipe/dynamo/tests` → 206 passed against unmodified uni-agent main.
`test_verl_logging_compat::test_pristine_upstream_setup_runs_with_info_enabled`
fails identically on untouched upstream (environment).

## Benchmark

2× L40S, one vLLM worker per GPU, Qwen2.5-7B, real KV capacity, 8k/6k-token
prefixes, 2k-token tool results, 6 subagent turns + 3 root turns, 2–6 s tool
gaps, 128-token outputs. Completion tokens/s, zero timeouts for every TA row:

| concurrency | ThunderAgent (this PR) | KV router | round-robin |
|---|---|---|---|
| 32  | 459.6 | 428.5 | 392.5 |
| 40  | 501.4 | 379.9 | 365.8 |
| 48  | 494.2 | 362.2 | 343.9 |
| 64  | 512.6 | 344.0 | 332.2 |
| 96  | 568.4 | 343.3 | 329.8 |
| 128 | 548.2 | 340.3 | 328.6 |

Without commit 4, ThunderAgent collapses at concurrency 40 (54 timeouts,
94.7 tok/s) because finished subagents hold admission for their starved
siblings. Repeat samples at 64 and 96 agree within ~4%.
