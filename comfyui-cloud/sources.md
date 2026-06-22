# ComfyUI Cloud Source Notes

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
