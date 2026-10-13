# ThunderAgent × Claude Code subagents · 8×H20 rollout-only 基准复现包

结果说明页：https://claude.ai/artifact/J2wyNAgAnu9tbfjZ2BR65y

## 代码仓库与分支

| 仓库 | 分支 / 版本 | 是否改动 |
|---|---|---|
| verl-recipe | `liz-badada/verl-recipe` 分支 [`feat/thunderagent-subagent-programs`](https://github.com/liz-badada/verl-recipe/tree/feat/thunderagent-subagent-programs)，HEAD `a75d4d9`，基于 upstream main `242c73f`，7 个 commit | **唯一改动的仓库** |
| uni-agent | `verl-project/uni-agent` main `1622670` | 不改动 |
| dynamo | nightly wheel `ai-dynamo[vllm]==1.6.0.dev20261009`（原生 Rust ThunderAgent 插件已在 upstream） | 不改动 |
| 本复现包 | 分支 `bench/ta-h20-harness`（本目录） | 基准脚本、数据、镜像 Dockerfile、原始结果 |

verl-recipe 的 7 个 commit：`fecf9b1` 每个 subagent 请求独立 X-Request-Id；`eb043bf` subagent 作为独立 program（身份头、父子关系、按 program 串行、释放规则）；`b9b8632` 评分器；`44b8fba` 返回即释放；`cab1e8b` `thunderagent.native=true` 接 Dynamo 原生 Rust 插件；`a19bdeb` 健康探针容忍 frontend 短暂 404；`a75d4d9` 网关适配器在不开 TA 时也保持 vLLM tool parser。开 PR：https://github.com/verl-project/verl-recipe/compare/main...liz-badada:verl-recipe:feat/thunderagent-subagent-programs

## 目录

- `ta-h20/`：8×H20 基准本体。`run_arm.sh <ta-native|kv|global> <run>` 跑一个臂；`run_all.sh [tag]` 烟测 + 三臂；`sweep_cc.sh` 并发扫描（折线图）；`summarize_run.py` / `compare_arms.py` / `time_to_512.py` / `count_agent_calls.py` / `final_report.py` 计分；`task_config_claude_code_docker*.yaml` 任务配置（默认 prompt / 强制派 3 个 subagent / computelab）；`data/convert_swe32.py` 生成 `data/swe_bench_verified_32_task.parquet`；`docker/Dockerfile` 最终镜像层；`overlay/handlers.py` 挂到容器内 `dynamo/vllm/handlers.py` 的 session_id 转发修正；`env.sh` 容器环境（NCCL_* 等）。
- `images/`：镜像链上游的三个 Dockerfile（uni-agent CI 基础镜像 → dynamo nightly CPU → dynamo nightly GPU）。
- `results/<run>/`：每轮每臂的 `summary.txt`、`summary.json`（逐 session 明细）、`command.txt`（完整启动命令与 SHA）、`agent_calls.log`、`frontend_metrics.prom`；`final_report_*.json` 为三轮汇总；`run_all-*.log` 为调度日志。
- `ta-e2e/`：此前 CPU/合成负载 e2e 与 subagent 负载脚本（分析页 https://claude.ai/artifact/7nvJSZG2AALBpED5WhU5mA 的数据来源），可选。

## 复现步骤

1. 机器：8× H20（141 GB），docker 可用，`/raid` 或等效的大容量 docker 存储（512 个并发 sandbox）。
2. 镜像：`verl-recipe-thunderagent:rust-ta-uniagent-20261012`。
   - 直接导入：`zstd -dc /lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20/xfer/image.tar.zst | docker load`（9.8 GB zst，同一 lustre 可见）。
   - 自建：`ta-h20/docker/Dockerfile` 在 `verl-recipe-thunderagent:pr11185-fa2.8.3-uni-agent-docker`（vllm 0.24 + flash-attn 2.8.3 + swe-rex，7 月 phase-1 镜像）之上叠 `dynamo-nightly-gpu:20261009` 的 dynamo 位；后者由 `images/` 三个 Dockerfile 依次构建。phase-1 基础镜像没有单一 Dockerfile，优先用导入方式。
3. 模型与 agent：`Qwen3-Coder-30B-A3B-Instruct`（`MODEL_DIR`）；Claude Code 2.1.296 单文件二进制，由任务 YAML 的 `run_args` 以只读方式挂到每个 sandbox 的 `/opt/claude-code/claude`（改成你的路径）。SWE-bench 沙箱镜像按 instance 自动拉取。
4. 代码：clone 上表的 verl-recipe 分支与 uni-agent main，设置 `RECIPE=... UNIAGENT=...`（`run_arm.sh` 以只读 bind-mount 进容器）。
5. 跑：
   ```bash
   export TA_H20_ROOT=$PWD/ta-h20
   # 第三轮口径：512 真实并发，默认 prompt，每卡 KV 60 GiB
   KV_BYTES=64424509440 RAY_NUM_CPUS=640 ARMS="ta-native global" SKIP_SMOKE=1 bash ta-h20/run_all.sh mytag
   # 第二轮口径：256 并发 + 强制 subagent prompt
   KV_BYTES=64424509440 RAY_NUM_CPUS=320 CONCURRENCY=256 TASK_CONFIG=/h20/task_config_claude_code_docker.subagents.yaml ARMS="ta-native global kv" SKIP_SMOKE=1 bash ta-h20/run_all.sh mytag
   # 并发扫描（折线图）
   bash ta-h20/sweep_cc.sh mytag
   ```
6. 计分：`python ta-h20/compare_arms.py auto runs/ta-native-X runs/global-X`（同一墙钟预算内前 BATCH×N 个 session），`python ta-h20/time_to_512.py runs/<run>`（trainer 口径：收齐 512 条轨迹用时），`python ta-h20/count_agent_calls.py runs/<run> <model_dir>`（解码 Agent 工具调用计 subagent 派生）。

## 三个臂

- `ta-native`：Dynamo frontend `--router-mode kv --router-policy-config <thunderagent.yaml>`，原生 Rust ThunderAgent 插件，recipe 的 Gateway 适配器（`thunderagent.native=true auto_finalize=false`）。
- `kv`：同一 Dynamo frontend，只开 KV router + sticky session，recipe 适配器 `thunderagent.enabled=false`。
- `global`：verl 自带 vLLM 副本 + `GlobalRequestLoadBalancer`，uni-agent 自己的适配器。

## 已知事项

- TA 默认 `resume_timeout_seconds: 1800` 在长 session 负载下偏长（每轮数百次到期强制恢复），可通过 `TA_PARAMS` 调。
- trainer 收齐轨迹后中止多余 session 时，适配器对仍在生成的 program 报 `TimeoutError … program was not released`，正式训练应在 abort 时释放 program（后续项）。
- 不要在脚本运行中原地编辑 `run_arm.sh`（bash 按偏移重读），改好后 `mv` 覆盖。
