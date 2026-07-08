"""Modal deployment for the Tier 3 model — a vLLM OpenAI-compatible server.

Deploy with:
    modal deploy backend/app/workers/modal_app.py

This starts vLLM's built-in OpenAI-compatible API server on Modal and
exposes it as an HTTPS endpoint (`modal deploy` prints the URL, something
like `https://<workspace>--hera-tier3-vllm-serve.modal.run`). Point
`agents/analysis_agent.py` at it by setting, in `.env`:

    HERA_TIER3_ENGINE=modal
    MODAL_VLLM_BASE_URL=https://<workspace>--hera-tier3-vllm-serve.modal.run/v1
    MODAL_VLLM_MODEL=google/gemma-3-4b-it   # must match MODEL_NAME below

`agents/analysis_agent.py` then talks to it via `pydantic_ai`'s
`OpenAIChatModel`/`OpenAIProvider` (see `models/llm.py::select_vllm_model`) —
no separate Modal-specific client code needed; it's the same agent, tools,
and prompt as the default cloud-model path, just pointed at a different
OpenAI-compatible base URL.
"""

from __future__ import annotations

import os

import modal

MODEL_NAME = os.environ.get("MODAL_VLLM_MODEL", "google/gemma-3-4b-it")

app = modal.App("hera-tier3-vllm")

image = (
    modal.Image.debian_slim()
    .pip_install("vllm")
    .env({"MODEL_NAME": MODEL_NAME})
)


@app.function(image=image, gpu="A10G", timeout=600, min_containers=1, scaledown_window=300)
@modal.concurrent(max_inputs=32)
@modal.web_server(port=8000, startup_timeout=300)
def serve():
    import subprocess

    subprocess.Popen(
        [
            "python",
            "-m",
            "vllm.entrypoints.openai.api_server",
            "--model",
            MODEL_NAME,
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--max-model-len",
            "8192",
        ]
    )
