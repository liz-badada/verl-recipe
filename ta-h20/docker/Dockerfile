# Trainer image for the 8xH20 rollout-only benchmark: the phase-1 verl/vLLM 0.24 environment
# (torch 2.11+cu130, flash-attn 2.8.3, docker CLI, swe-rex) plus a Dynamo build that ships the
# native Rust ThunderAgent plugin (nightly 2026-09-24, first nightly after it merged on 09-23),
# installed without the [vllm] extra so vLLM 0.24 stays, with the recipe's vLLM 0.24 patch
# (THUNDERAGENT_VLLM024.md) applied to the installed worker. Code is bind-mounted at run time.
FROM dynamo-nightly-gpu:20261009 AS dynamo-bits
FROM verl-recipe-thunderagent:pr11185-fa2.8.3-uni-agent-docker
USER root
COPY --from=dynamo-bits /usr/local/lib/libavcodec_dynamo.so* /usr/local/lib/libavdevice_dynamo.so* \
     /usr/local/lib/libavfilter_dynamo.so* /usr/local/lib/libavformat_dynamo.so* /usr/local/lib/libavutil_dynamo.so* \
     /usr/local/lib/libswresample_dynamo.so* /usr/local/lib/libswscale_dynamo.so* /usr/local/lib/
RUN ldconfig && apt-get update -qq && apt-get install -y -qq --no-install-recommends git patch > /dev/null && rm -rf /var/lib/apt/lists/*
COPY constraints.txt dynamo-client-errors.patch /tmp/
# ai-dynamo's metadata pulls aisimulate (and with it JAX) for dynamo.replay only; install the
# two wheels without deps and add the runtime deps the frontend and vLLM worker import.
RUN python -m pip install --no-cache-dir --no-deps --pre \
        "ai-dynamo==1.6.0.dev20260924" "ai-dynamo-runtime==1.6.0.dev20260924" \
    && python -m pip install --no-cache-dir -c /tmp/constraints.txt \
        "aiohttp>=3.14.3,<4" "msgspec>=0.19.0" "prometheus-client>=0.23.1,<1" "pyzmq>=26" "redis>=6.2,<9" \
        "zstandard>=0.23,<1" "kubernetes>=32.0.1,<33" "typing-extensions>=4.10" uvloop "pydantic>=2" \
        "transformers==5.5.3" "accelerate==1.15.0" "protobuf>=6.33.5,<7" "grpcio-tools==1.81.1" blake3 \
        "nixl[cu13]==1.3.2" "cupy-cuda13x==14.0.1" \
        "TransferQueue @ git+https://github.com/Ascend/TransferQueue.git@434f8c476b4be24bc087e6e95070e64efcc739f9" \
        fastapi uvicorn cachetools loguru pytest pytest-asyncio
RUN cd "$(python -c 'import sysconfig;print(sysconfig.get_paths()["purelib"])')" \
    && patch -p3 < /tmp/dynamo-client-errors.patch \
    && python -c "import dynamo._core, dynamo.frontend, dynamo.vllm.main, transfer_queue, vllm, torch, transformers; print('vllm', vllm.__version__, 'torch', torch.__version__, 'transformers', transformers.__version__)" \
    && python -m dynamo.frontend --help | grep -q -- --router-policy-config && echo "router-policy-config OK"
# The benchmark runs the container as the host user so run dirs on NFS stay writable.
RUN groupadd -g 1015 jinyanc && useradd -u 1015 -g 1015 -m jinyanc
# vLLM 0.24's AsyncLLM.generate has no session_id parameter; forward it only when supported.
COPY handlers.py /usr/local/lib/python3.12/dist-packages/dynamo/vllm/handlers.py
