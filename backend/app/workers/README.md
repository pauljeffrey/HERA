# Tier 3 worker: self-hosted vLLM on Modal

`modal_app.py` deploys vLLM's OpenAI-compatible API server on Modal, serving
`google/gemma-3-4b-it` (or whatever `MODAL_VLLM_MODEL` is set to) on a single
A10G GPU.

```
modal deploy backend/app/workers/modal_app.py
```

This prints an HTTPS URL (something like
`https://<workspace>--hera-tier3-vllm-serve.modal.run`). Set it in `.env`:

```
HERA_TIER3_ENGINE=modal
MODAL_VLLM_BASE_URL=https://<workspace>--hera-tier3-vllm-serve.modal.run/v1
MODAL_VLLM_MODEL=google/gemma-3-4b-it
```

There's no separate Modal client code — `agents/analysis_agent.py` builds
an `OpenAIChatModel` pointed at `MODAL_VLLM_BASE_URL`
(`models/llm.py::select_vllm_model`) and runs the exact same agent, tools,
and prompt as the default cloud-model path. Leave `HERA_TIER3_ENGINE` unset
(or `api`) to use the default cloud model (`MODEL_NAME`/`MODEL_API_KEY`)
instead — that's the default, Modal is opt-in only.
