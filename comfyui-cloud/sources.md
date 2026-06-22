# ComfyUI Cloud / Local Source Notes

This file captures the current public documentation facts that drive the integration plan. Re-check these before implementing because Comfy Cloud API documentation marks the API as experimental.

## Comfy Cloud API

Source: https://docs.comfy.org/development/cloud/overview

Key facts:

- Base URL: `https://cloud.comfy.org`
- Authentication: `X-API-Key: $COMFY_CLOUD_API_KEY`
- Workflows are submitted in Comfy API workflow format, not the UI graph format.
- Submit workflow: `POST /api/prompt`
- Response includes `prompt_id`.
- Jobs are asynchronous.
- Poll status: `GET /api/job/{prompt_id}/status`
- Status values include `pending`, `in_progress`, `completed`, `failed`, `cancelled`.
- Output metadata can be collected through WebSocket events or job detail.
- Outputs are downloaded through `/api/view`, which redirects to a temporary signed URL.
- API access requires paid Comfy Cloud tier; free tier does not include API access.
- API jobs use the same Comfy Cloud credits as the web UI.
- The Comfy API key used for Partner Nodes can also be used as the hosted Cloud API `X-API-Key` header.
- Concurrency is subscription-tier dependent.
- The API is experimental and may change.

## Comfy Partner Nodes

Source: https://docs.comfy.org/tutorials/partner-nodes/overview

Key facts:

- Partner Nodes connect to external hosted AI services inside Comfy workflows.
- They are designed to avoid managing many vendor API keys in the caller.
- They require Comfy account login/API key and sufficient credits.
- They are opt-in and can be combined with ordinary Comfy nodes.
- Partner Nodes are the right abstraction for using closed-source/cloud models from Godogen through Comfy.

## Local ComfyUI Server And API Nodes

Sources:

- Local install inspected from `/Users/ddm/Documents/ComfyUI` at ComfyUI `v0.25.1`
- Source example: `/Users/ddm/Documents/ComfyUI/script_examples/basic_api_example.py`
- Source implementation: `/Users/ddm/Documents/ComfyUI/comfy_api/latest/_io.py`
- Source implementation: `/Users/ddm/Documents/ComfyUI/comfy_api_nodes/nodes_openrouter.py`

Key facts:

- Local ComfyUI source install serves workflow API calls through `POST /prompt`, history through `GET /history/{prompt_id}`, and file download through `GET /view`.
- API-format workflows are still required; UI graph JSON is not the submission format.
- API nodes expose hidden `AUTH_TOKEN_COMFY_ORG` and `API_KEY_COMFY_ORG` fields.
- Browser login supplies an auth token for UI-run workflows, but direct CLI/API submission does not automatically reuse that browser login.
- Programmatic Partner/API node submission should pass a Comfy account API key through `extra_data.api_key_comfy_org`; Godogen reads this from `COMFY_API_KEY` and never stores it in sidecars.
- ComfyUI Desktop is not required for programmatic execution. A source install that exposes `POST /prompt` can run paid Partner/API nodes when the payload includes `extra_data.api_key_comfy_org`.
- `OpenRouterLLMNode` uses `COMFY_DYNAMICCOMBO_V3`; API workflow input should set `inputs.model` to the selected model string and nested option fields as dotted keys such as `inputs.model.reasoning_effort`.
- A direct `/prompt` probe without `COMFY_API_KEY` against a paid Partner node returned `Unauthorized: Please login first to use this node.`, confirming that UI login is not sufficient for Codex CLI automation.

## LLM Nodes

OpenRouter LLM source: https://docs.comfy.org/tutorials/partner-nodes/openrouter/llm

Key facts:

- Comfy has an OpenRouter LLM Partner Node.
- It supports chat, reasoning, vision, optional video input on supported models, and web-grounded answers.
- It exposes multiple frontier model families behind one node, including Claude, GPT, Gemini, Grok, DeepSeek, Qwen, Mistral, GLM, Kimi, and Perplexity Sonar.

Anthropic Claude source: https://docs.comfy.org/tutorials/partner-nodes/anthropic/claude

Key facts:

- Comfy has Anthropic Claude Partner Nodes.
- Claude nodes support conversational and image-analysis workflows.
- Official examples mention model selection, prompt, optional system prompt, and multimodal inputs.

OpenAI Chat source: https://docs.comfy.org/tutorials/partner-nodes/openai/chat

Key facts:

- Comfy has OpenAI Chat Partner Nodes.
- These can be used inside workflows for conversational functions and image interpretation.

Architecture implication:

- LLMs can exist inside Comfy workflows for prompt expansion, image analysis, metadata generation, and workflow-internal decisions.
- Codex should remain the project orchestrator because it owns repo edits, tests, engine runs, git, and acceptance.
- `llm-smoke` is the lowest-cost practical paid-path smoke because it uses short text through OpenRouter rather than image/video/3D generation.

## Image, Video, And 3D Nodes

Hunyuan 3D source: https://docs.comfy.org/tutorials/partner-nodes/hunyuan3d/hunyuan3d-3-0

Key facts:

- Comfy has Hunyuan 3D Partner Nodes.
- Official docs describe text-to-3D, image-to-3D, and multi-view-to-3D workflows.
- Use cases include game development ideation, high-resolution assets, professional UVs, and PBR materials.

Tripo in Comfy source: https://comfy.org/p/supported-models/tripo-3d/

Key facts:

- Tripo is accessible through Comfy Partner Nodes.
- It can be connected with other Comfy nodes and workflow templates.

Tripo custom node source: https://github.com/VAST-AI-Research/ComfyUI-Tripo

Key facts:

- The Tripo Comfy extension supports text prompts, image prompts, multi-view images, texturing/PBR, refinement, conversion, retopology, and animation.
- This supports keeping direct Tripo API as fallback while validating Comfy-based Tripo profiles.

## Comfy Workflow API Format

Implementation must use exported API-format workflow JSON. Do not rely on UI-only workflow JSON.

Workflow profiles should specify:

- profile id
- asset kind
- workflow JSON path
- input bindings to replace before submission
- output node ids
- expected file extensions
- timeout
- whether the workflow can consume paid credits
- validation rule for downloaded outputs
