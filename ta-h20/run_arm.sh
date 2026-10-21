#!/bin/bash
# run_arm.sh <ta-native|kv|global> <run-name>: one arm of the rollout-only UniAgent benchmark on 8xH20.
#   ta-native : Dynamo frontend, KV router + native Rust ThunderAgent plugin, recipe Gateway adapter
#   kv        : Dynamo frontend, KV router with sticky sessions, Uni-Agent's own adapter
#   global    : verl native vLLM replicas behind GlobalRequestLoadBalancer, Uni-Agent's own adapter
# Claude Code (subagents on) solves 32 SWE-bench Verified instances x N rollouts in docker sandboxes.
# The run is stopped once every session's trajectory has landed, before the training step.
set -euo pipefail
ARM=${1:?ta-native|kv|global}; RUN_NAME=${2:?run name}; shift 2
H=${TA_H20_ROOT:-/lustre/raplab/client/jinyanc/workspace/jinyanc/ci/ta-h20}
ENGINE=${ENGINE:-vllm}            # vllm | sglang: the inference engine behind every arm (image, trainer config and engine flags follow)
# STACK selects the software stack around the engine. uniagent (default): Uni-Agent's verl submodule (1622670 / its verl),
# recipe 33fac10, vLLM 0.24.0 or SGLang 0.5.19 images. verl010: the verlai/verl uv.cu130.dev4 image (verl 0.10.0.dev0,
# vLLM 0.29.0, torch 2.13 + cu130) with recipe b85e1b7 and Uni-Agent 4f3cd34 (PR #270), the stack of
# recipe/dynamo/THUNDERAGENT_VLLM.md; vLLM only. Engine flags, KV cap and the bench settings are the same in both.
STACK=${STACK:-uniagent}
case $STACK in
  uniagent) UNIAGENT=${UNIAGENT:-/home/jinyanc/workspace/jinyanc/github/uni-agent}
            RECIPE=${RECIPE:-/home/jinyanc/workspace/jinyanc/github/verl-recipe}
            VERL_DIR=/workspace/uni-agent/verl; PYPATH=/workspace/recipe-root:/workspace/uni-agent/verl:/workspace/uni-agent
            EXT_MODULES=recipe.dynamo.register;;
  verl010)  [ "$ENGINE" = vllm ] || { echo "STACK=verl010 is vLLM only" >&2; exit 2; }
            UNIAGENT=${UNIAGENT:-$H/uni-agent-4f3cd34}
            RECIPE=${RECIPE:-$H/../recipe-v029}
            IMAGE=${IMAGE:-verl-recipe-thunderagent:vllm029-uniagent-20261020}
            TASK_CONFIG=${TASK_CONFIG:-/h20/task_config_claude_code_docker.v029.yaml}
            VERL_DIR=/workspace/verl; PYPATH=/workspace/verl:/workspace/recipe-root:/workspace/uni-agent
            EXT_MODULES=recipe.dynamo.register,recipe.dynamo.verl_logging_compat
            # verl 0.10's transfer_queue.yaml leaves total_storage_size null ("unlimited"), but the TransferQueue 0.1.11 it
            # installs divides it by num_data_storage_units at init and dies on None; give it a capacity (samples, not bytes).
            TQ_SIZE=65536;;
  *) echo "STACK must be uniagent or verl010, got $STACK" >&2; exit 2;;
esac
case $ENGINE in
  vllm)   IMAGE=${IMAGE:-verl-recipe-thunderagent:rust-ta-uniagent-20261012}; FSDP_RMPAD=true; SP=4;;
  # The SGLang image (torch 2.13 + cu130) has no flash-attn wheel, so the FSDP actor loads with SDPA, without
  # remove-padding and therefore without sequence parallel (verl rejects SP>1 with padding). The train step never
  # runs in this rollout-only bench, so neither setting touches the measured rollout engine.
  sglang) IMAGE=${IMAGE:-verl-recipe-thunderagent:rust-ta-uniagent-sglang-20261018b}; FSDP_RMPAD=false; SP=1;;
  *) echo "ENGINE must be vllm or sglang, got $ENGINE" >&2; exit 2;;
esac
MODEL_DIR=${MODEL_DIR:-/home/jinyanc/workspace/model/hub/Qwen3-Coder-30B-A3B-Instruct}
MODEL_NAME=${MODEL_NAME:-$(basename "$MODEL_DIR")}
DATA=${DATA:-/h20/data/swe_bench_verified_32_task.parquet}
TASK_CONFIG=${TASK_CONFIG:-/h20/task_config_claude_code_docker.yaml}
BATCH=${BATCH:-32}; N=${N:-16}; CONCURRENCY=${CONCURRENCY:-512}
MAX_PROMPT=${MAX_PROMPT:-8192}; MAX_RESP=${MAX_RESP:-65536}
# sglang has no byte cap, so KV_BYTES is ignored there and the KV pool is pinned in tokens instead: vLLM's 60 GiB cap
# gives 2,621,440 tokens per TP4 engine for this model, and both sglang arms get exactly that pool (--max-total-tokens;
# mem_fraction_static 0.78 alone would leave ~3.76M tokens, ~87 GiB per GPU, which the 10160955 sglang runs had).
GPU_MEM=${GPU_MEM:-$([ "$ENGINE" = sglang ] && echo 0.78 || echo 0.75)}; MAX_NUM_SEQS=${MAX_NUM_SEQS:-256}; TP=${TP:-4}
SG_MAX_TOTAL_TOKENS=${SG_MAX_TOTAL_TOKENS:-2621440}
# H100 80 GB: the FSDP trainer already holds ~12 GiB/GPU when the engines start, so 0.92 (72.9 GiB) never fits
# (free 66.8-68.2 GiB). 0.80 = 63.4 GiB, with a 44 GiB KV cap shared by both arms (H20 uses 60 GiB of its 96).
if [ "${SITE:-h20}" = h100 ]; then GPU_MEM=0.80; KV_BYTES=47244640256; fi
TEMP=${TEMP:-0.8}; TOP_P=${TOP_P:-0.9}
GATEWAY_COUNT=${GATEWAY_COUNT:-8}; RAY_NUM_CPUS=${RAY_NUM_CPUS:-128}
KV_BYTES=${KV_BYTES:-}            # optional per-GPU KV cap (bytes); empty = gpu_memory_utilization
DISABLE_CUSTOM_AR=${DISABLE_CUSTOM_AR:-}  # set to 1 on nodes whose GPU P2P path hangs: TP all-reduce goes through NCCL
TA_PARAMS=${TA_PARAMS:-'{scheduler_interval_seconds: 1, resume_timeout_seconds: 1800}'}
RUN=$H/runs/$RUN_NAME
# Site-specific container env (e.g. NCCL_* for the node), one "-e NAME=VALUE" per line in env.sh.
SITE_ENV=(); [ -f "$H/env.sh" ] && while read -r kv; do [ -n "$kv" ] && SITE_ENV+=(-e "$kv"); done < "$H/env.sh"
[ -e "$RUN/command.txt" ] && { echo "run exists: $RUN" >&2; exit 4; }
mkdir -p "$RUN"/{agent_logs,dynamo,home,hydra,worker_metrics,ray}
NS=$(echo "$RUN_NAME" | tr -c 'a-zA-Z0-9_\n' '_')
EXPECTED=$((BATCH * N)); ARM_T0=$(date +%s)

common=(
  trainer.use_v1=true trainer.v1.trainer_mode=colocate_async
  trainer.v1.colocate_async.num_warmup_batches=1
  transfer_queue.enable=true ${TQ_SIZE:+"++transfer_queue.backend.SimpleStorage.total_storage_size=$TQ_SIZE"}
  algorithm.adv_estimator=grpo algorithm.use_kl_in_reward=false
  algorithm.rollout_correction.bypass_mode=true algorithm.rollout_correction.loss_type=ppo_clip
  "data.train_files='$DATA'" "data.val_files='$DATA'"
  data.return_raw_chat=true "data.train_batch_size=$BATCH"
  "data.max_prompt_length=$MAX_PROMPT" "data.max_response_length=$MAX_RESP"
  data.filter_overlong_prompts=true data.filter_overlong_prompts_workers=1
  data.truncation=error data.shuffle=false data.seed=42
  "actor_rollout_ref.model.path=/model"
  "actor_rollout_ref.model.use_remove_padding=$FSDP_RMPAD"
  actor_rollout_ref.model.enable_gradient_checkpointing=true
  actor_rollout_ref.actor.strategy=fsdp2
  actor_rollout_ref.actor.optim.lr=1e-6
  ++actor_rollout_ref.actor.optim.override_optimizer_config.foreach=false
  actor_rollout_ref.actor.use_kl_loss=false
  actor_rollout_ref.actor.use_dynamic_bsz=true
  "actor_rollout_ref.actor.ppo_mini_batch_size=$BATCH"
  actor_rollout_ref.actor.ppo_micro_batch_size_per_gpu=1
  "actor_rollout_ref.actor.ppo_max_token_len_per_gpu=$((MAX_PROMPT + MAX_RESP))"
  "actor_rollout_ref.actor.ulysses_sequence_parallel_size=$SP"
  actor_rollout_ref.actor.use_torch_compile=false
  actor_rollout_ref.actor.entropy_from_logits_with_chunking=true
  actor_rollout_ref.actor.fsdp_config.use_torch_compile=false
  "actor_rollout_ref.actor.fsdp_config.param_offload=${PARAM_OFFLOAD:-false}"
  # bf16 master copy: fp32 would hold 8 x 122 GB of HF weights in host RAM during the FSDP2 broadcast
  "actor_rollout_ref.actor.fsdp_config.model_dtype=${MODEL_DTYPE:-bf16}"
  actor_rollout_ref.actor.fsdp_config.optimizer_offload=true
  actor_rollout_ref.actor.fsdp_config.fsdp_size=8
  actor_rollout_ref.actor.fsdp_config.use_no_sync_for_gradient_accumulation=false
  actor_rollout_ref.rollout.mode=async
  "actor_rollout_ref.rollout.tensor_model_parallel_size=$TP"
  actor_rollout_ref.rollout.nnodes=0
  "actor_rollout_ref.rollout.gpu_memory_utilization=$GPU_MEM"
  "actor_rollout_ref.rollout.max_model_len=$((MAX_PROMPT + MAX_RESP))"
  actor_rollout_ref.rollout.max_num_batched_tokens=32768
  "actor_rollout_ref.rollout.max_num_seqs=$MAX_NUM_SEQS"
  actor_rollout_ref.rollout.disable_log_stats=false
  "actor_rollout_ref.rollout.temperature=$TEMP" "actor_rollout_ref.rollout.top_p=$TOP_P"
  actor_rollout_ref.rollout.top_k=-1 "actor_rollout_ref.rollout.n=$N"
  actor_rollout_ref.rollout.enable_prefix_caching=true
  actor_rollout_ref.rollout.enforce_eager=false
  actor_rollout_ref.rollout.free_cache_engine=true
  actor_rollout_ref.rollout.calculate_log_probs=true
  actor_rollout_ref.rollout.log_prob_micro_batch_size_per_gpu=1
  actor_rollout_ref.rollout.agent.num_workers=8
  actor_rollout_ref.rollout.multi_turn.enable=true
  actor_rollout_ref.rollout.multi_turn.format=qwen3_coder
  actor_rollout_ref.rollout.agent.default_agent_loop=task
  actor_rollout_ref.rollout.agent.agent_loop_config_path=null
  "++actor_rollout_ref.rollout.custom.agent_framework.gateway_count=$GATEWAY_COUNT"
  "++actor_rollout_ref.rollout.custom.agent_framework.log_dir=/bench_run/agent_logs"
  ++actor_rollout_ref.rollout.custom.agent_framework.agent_runners.task.runner_fqn=uni_agent.framework.task_runner.run_task
  ++actor_rollout_ref.rollout.custom.agent_framework.agent_runners.task.dispatch_mode=ray_task
  "++actor_rollout_ref.rollout.custom.agent_framework.agent_runners.task.max_concurrent_sessions=$CONCURRENCY"
  ++actor_rollout_ref.rollout.custom.agent_framework.agent_runners.task.trajectory_selection=longest
  "++actor_rollout_ref.rollout.custom.agent_framework.agent_runners.task.runner_kwargs.task_config_path='$TASK_CONFIG'"
  "++actor_rollout_ref.rollout.custom.agent_framework.agent_runners.task.runner_kwargs.model_name='$MODEL_NAME'"
  '++actor_rollout_ref.rollout.custom.agent_framework.allowed_request_sampling_param_keys=[temperature,top_p,top_k]'
  'trainer.logger=[console]' trainer.project_name=ta-h20-uniagent "trainer.experiment_name='$RUN_NAME'"
  trainer.nnodes=1 trainer.n_gpus_per_node=8
  trainer.val_before_train=false trainer.test_freq=-1 trainer.save_freq=-1
  trainer.total_epochs=1 trainer.total_training_steps=1 trainer.resume_mode=disable
  "trainer.default_local_dir=/bench_run/checkpoints" "trainer.rollout_data_dir=/bench_run/rollouts"
  ++ray_kwargs.ray_init.address=null "ray_kwargs.ray_init.num_cpus=$RAY_NUM_CPUS"
  ++ray_kwargs.ray_init.runtime_env.py_executable=null
  "hydra.run.dir=/bench_run/hydra"
)
# sglang weight sync: the recipe posts every bucket's CUDA-IPC handles as JSON to the dynamo worker's system server,
# with all TP ranks' handles in each of TP blobs (payload ~ TP^2 x tensors x 260 B). Behind axum's 2 MiB body limit
# a 2048 MiB bucket of this MoE's 3 MiB expert tensors is HTTP 413; 256 MiB keeps every request under 0.5 MiB.
[ "$ENGINE" = sglang ] && common+=(+actor_rollout_ref.model.override_config.attn_implementation=sdpa
                                   "actor_rollout_ref.rollout.checkpoint_engine.update_weights_bucket_megabytes=${WEIGHT_BUCKET_MB:-256}")
env=(-e HOME=/bench_run/home -e USER=$(id -un) -e LOGNAME=$(id -un) -e "PYTHONPATH=$PYPATH" -e TOKENIZERS_PARALLELISM=false -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1
     -e RAY_DEDUP_LOGS=0 -e HYDRA_FULL_ERROR=1 -e VERL_DYNAMO_LOG_DIR=/bench_run/dynamo -e VERL_DYNAMO_WORKER_METRICS_DIR=/bench_run/worker_metrics
     -e VERL_DYNAMO_FE_READY_TIMEOUT=1800 -e VLLM_LOGGING_LEVEL=INFO)
rt=("++ray_kwargs.ray_init.runtime_env.env_vars.PYTHONPATH='$PYPATH'" "++ray_kwargs.ray_init.runtime_env.env_vars.VERL_DYNAMO_LOG_DIR=/bench_run/dynamo"
    "++ray_kwargs.ray_init.runtime_env.env_vars.VERL_DYNAMO_WORKER_METRICS_DIR=/bench_run/worker_metrics")
# Engine-specific pieces. vLLM: seed, router block size, admission and the KV byte cap on the command line, plus the
# patched dynamo.vllm handlers overlay. sglang: --page-size and --max-running-requests come from the recipe config
# (router_block_size, max_num_seqs); the seed flag is spelled --random-seed; no overlay.
case $ENGINE in
  vllm)   ENGINE_CFG_SUFFIX=""
          ENGINE_EXTRA_ARGS="[--seed,42,--block-size,16,--max-num-seqs,$MAX_NUM_SEQS${DISABLE_CUSTOM_AR:+,--disable-custom-all-reduce}${KV_BYTES:+,--kv-cache-memory-bytes,$KV_BYTES}]"
          # the overlay withholds session_id from an engine generate() that lacks it (vLLM < 0.28); vLLM 0.29 takes it
          OVERLAY=(-v "$H/overlay/handlers.py":/usr/local/lib/python3.12/dist-packages/dynamo/vllm/handlers.py:ro); [ "$STACK" = verl010 ] && OVERLAY=();;
  sglang) ENGINE_CFG_SUFFIX="_sglang"
          ENGINE_EXTRA_ARGS="[--random-seed,42,--max-total-tokens,$SG_MAX_TOTAL_TOKENS${DISABLE_CUSTOM_AR:+,--disable-custom-all-reduce}]"
          OVERLAY=();;
esac
case $ARM in
  global)
    arm=("actor_rollout_ref.rollout.name=$ENGINE"
         ++actor_rollout_ref.rollout.agent.agent_loop_manager_class=uni_agent.framework.entry.AgentFrameworkRolloutAdapter)
    [ "$ENGINE" = vllm ] && [ -n "$KV_BYTES" ] && arm+=("+actor_rollout_ref.rollout.engine_kwargs.vllm.kv_cache_memory_bytes=$KV_BYTES")
    [ -n "${DISABLE_CUSTOM_AR:-}" ] && arm+=("+actor_rollout_ref.rollout.engine_kwargs.$ENGINE.disable_custom_all_reduce=true")
    # verl's native sglang server hardcodes log_level=error, which silences the scheduler's throughput lines that
    # engine_rate.py reads (the dynamo arms log them at info); engine_kwargs is merged last, so this wins.
    [ "$ENGINE" = sglang ] && arm+=("+actor_rollout_ref.rollout.engine_kwargs.sglang.log_level=info")
    # Same KV pool and the same scheduler-facing args as the dynamo.sglang worker of the TA arm (which takes
    # --context-length / --chunked-prefill-size / --page-size from max_model_len, max_num_batched_tokens and
    # router_block_size); verl's native server would otherwise start with 8192-token chunks, page_size 1 and no
    # context cap.
    [ "$ENGINE" = sglang ] && arm+=("+actor_rollout_ref.rollout.engine_kwargs.sglang.max_total_tokens=$SG_MAX_TOTAL_TOKENS"
                                     "+actor_rollout_ref.rollout.engine_kwargs.sglang.chunked_prefill_size=32768"
                                     "+actor_rollout_ref.rollout.engine_kwargs.sglang.page_size=16"
                                     "+actor_rollout_ref.rollout.engine_kwargs.sglang.context_length=$((MAX_PROMPT + MAX_RESP))")
    ;;
  kv|ta-native)
    env+=(-e "VERL_USE_EXTERNAL_MODULES=$EXT_MODULES")
    rt+=("++ray_kwargs.ray_init.runtime_env.env_vars.VERL_USE_EXTERNAL_MODULES='$EXT_MODULES'")
    arm=(--config-path /workspace/recipe-root/recipe/dynamo/config --config-name "dynamo_trainer_v1_colocate${ENGINE_CFG_SUFFIX:-}"
         actor_rollout_ref.rollout.name=dynamo
         "++actor_rollout_ref.rollout.engine_kwargs.dynamo.engine=$ENGINE"
         ++actor_rollout_ref.rollout.engine_kwargs.dynamo.router_mode=kv
         ++actor_rollout_ref.rollout.engine_kwargs.dynamo.enable_kv_events=true
         ++actor_rollout_ref.rollout.engine_kwargs.dynamo.router_session_affinity_ttl_secs=1800
         ++actor_rollout_ref.rollout.engine_kwargs.dynamo.direct_generate=false
         ++actor_rollout_ref.rollout.engine_kwargs.dynamo.request_engine_data=true
         ++actor_rollout_ref.rollout.engine_kwargs.dynamo.request_completion_token_ids=true
         ++actor_rollout_ref.rollout.engine_kwargs.dynamo.request_timeout_s=7200
         ++actor_rollout_ref.rollout.engine_kwargs.dynamo.enable_worker_system_metrics=true
         ++actor_rollout_ref.rollout.engine_kwargs.dynamo.stable_kv_event_ports=true
         ++actor_rollout_ref.rollout.engine_kwargs.dynamo.free_engine_on_train=true
         "++actor_rollout_ref.rollout.engine_kwargs.dynamo.namespace='$NS'"
         ++actor_rollout_ref.rollout.engine_kwargs.dynamo.thunderagent.router_block_size=16
         "++actor_rollout_ref.rollout.engine_kwargs.dynamo.extra_args=$ENGINE_EXTRA_ARGS"
         '++actor_rollout_ref.rollout.engine_kwargs.dynamo.frontend_extra_args=[--kv-cache-block-size,16]')
    if [ $ARM = ta-native ]; then
      arm+=(++actor_rollout_ref.rollout.engine_kwargs.dynamo.thunderagent.enabled=true
            ++actor_rollout_ref.rollout.engine_kwargs.dynamo.thunderagent.native=true
            ++actor_rollout_ref.rollout.engine_kwargs.dynamo.thunderagent.auto_finalize=false
            "++actor_rollout_ref.rollout.engine_kwargs.dynamo.thunderagent.native_parameters=$TA_PARAMS"
            ${SUBAGENT_PROGRAMS:+++actor_rollout_ref.rollout.engine_kwargs.dynamo.thunderagent.subagent_programs=$SUBAGENT_PROGRAMS}
            actor_rollout_ref.rollout.agent.agent_loop_manager_class=recipe.dynamo.uniagent_gateway.DynamoAgentFrameworkRolloutAdapter)
    else
      # Dynamo KV router baseline: the recipe adapter without ThunderAgent keeps the vLLM tool parser
      arm+=(++actor_rollout_ref.rollout.engine_kwargs.dynamo.thunderagent.enabled=false
            actor_rollout_ref.rollout.agent.agent_loop_manager_class=recipe.dynamo.uniagent_gateway.DynamoAgentFrameworkRolloutAdapter)
    fi
    ;;
  *) echo "unknown arm $ARM" >&2; exit 2;;
esac

{
  echo "SITE_ENV=${SITE_ENV[*]}"
  echo "ARM=$ARM ENGINE=$ENGINE STACK=$STACK RUN_NAME=$RUN_NAME BATCH=$BATCH N=$N CONCURRENCY=$CONCURRENCY MAX_PROMPT=$MAX_PROMPT MAX_RESP=$MAX_RESP GPU_MEM=$GPU_MEM MAX_NUM_SEQS=$MAX_NUM_SEQS TP=$TP KV_BYTES=$KV_BYTES TA_PARAMS=$TA_PARAMS MODEL_DIR=$MODEL_DIR IMAGE=$IMAGE"
  echo "SUBAGENT_PROGRAMS=${SUBAGENT_PROGRAMS:-tree}"
  echo "HOST=$(hostname) UNIAGENT_SHA=$(git -C $UNIAGENT rev-parse HEAD) RECIPE_SHA=$(git -C $RECIPE rev-parse HEAD) CLAUDE=$(readlink -f ~/.local/bin/claude) START_EPOCH=$(date +%s)"
  echo "python -m verl.trainer.main_ppo ${arm[*]} ${common[*]} ${rt[*]} $*"
} > "$RUN/command.txt"
[ -n "${DRY_RUN:-}" ] && { cat "$RUN/command.txt"; rm -rf "$RUN"; exit 0; }

printf 'timestamp,index,utilization_gpu_pct,memory_used_mib,power_draw_w\n' > "$RUN/gpu.csv"
( while true; do ts=$(date +%s.%N); nvidia-smi --query-gpu=index,utilization.gpu,memory.used,power.draw --format=csv,noheader,nounits | while IFS= read -r row; do printf '%s,%s\n' "$ts" "${row//, /,}"; done; sleep 1; done ) >> "$RUN/gpu.csv" 2>/dev/null &
SAMPLER=$!
( while true; do nvidia-smi --query-compute-apps=pid,gpu_uuid,used_memory,process_name --format=csv,noheader | sed "s/^/$(date +%s),/"; sleep 60; done ) >> "$RUN/gpu_procs.csv" 2>/dev/null &
PROC_SAMPLER=$!
# Rollout-only: stop the container once every session has a trajectory dump (the train step is not measured).
( set +e  # the loop must survive empty globs under the script's errexit/pipefail
  while sleep 15; do
    # count finished sessions among the first EXPECTED started (the trainer keeps prefetching prompt groups)
    # Bounded: on a node whose sandboxes keep failing the framework piles up retry directories and the scan
    # would otherwise outlast the wall cap it is meant to enforce.
    n=$(timeout 120 python3 "$H/first_n_done.py" "$RUN" "$EXPECTED" 2>/dev/null | awk '{print $1+0}')
    docker ps -q --filter "name=^$RUN_NAME$" | grep -q . || break
    # stop when the first EXPECTED sessions are all done, or at the wall cap (same rule for every arm)
    if [ "$n" -ge "$EXPECTED" ] || [ $(( $(date +%s) - ARM_T0 )) -ge "${ROLLOUT_MAX_S:-10800}" ] || grep -q 'generate_sequences summary' "$RUN/console.log" 2>/dev/null; then
      sleep 30; echo "ROLLOUT_DONE_EPOCH=$(date +%s) sessions=$n" >> "$RUN/command.txt"
      # Router-side counters before the stack goes away (Dynamo arms only).
      port=$(grep -o 'starting dynamo.frontend on :[0-9]*' "$RUN/console.log" | head -1 | grep -o '[0-9]*$')
      [ -n "$port" ] && curl -s -m 10 "http://127.0.0.1:$port/metrics" > "$RUN/frontend_metrics.prom" 2>/dev/null
      docker rm -f "$RUN_NAME" >/dev/null 2>&1; break
    fi
  done ) &
WATCHER=$!
cleanup() { kill $SAMPLER $PROC_SAMPLER $WATCHER 2>/dev/null; docker ps -q --filter name=uni-agent- | xargs -r docker rm -f >/dev/null 2>&1; }
trap cleanup EXIT

docker run --rm --name "$RUN_NAME" --network host --gpus all --ipc=host --shm-size 64g \
  --user "$(id -u):$(id -g)" --group-add "$(stat -c '%g' /var/run/docker.sock)" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$UNIAGENT":/workspace/uni-agent:ro -v "$RECIPE":/workspace/recipe-root/recipe:ro \
  -v "$MODEL_DIR":/model:ro -v "$H":/h20:ro -v "$RUN":/bench_run -v "$RUN/ray":/tmp/ray \
  "${OVERLAY[@]}" \
  "${env[@]}" "${SITE_ENV[@]}" -w "$VERL_DIR" "$IMAGE" \
  python -m verl.trainer.main_ppo "${arm[@]}" "${common[@]}" "${rt[@]}" "$@" 2>&1 | tee "$RUN/console.log" || true
echo "END_EPOCH=$(date +%s)" >> "$RUN/command.txt"
python3 "$H/summarize_run.py" "$RUN" | tee "$RUN/summary.txt"
