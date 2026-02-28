"""Self-hosted LLM — Qwen3-8B via vLLM on H100 GPU.

Provides streaming and non-streaming text generation for the Alethia reasoning engine.
Modal features: @modal.cls, @modal.enter, @modal.concurrent, gpu=H100, Image.run_commands()
"""
from __future__ import annotations
import uuid

import modal

from modal_app.volume import app, volume, weights_volume, vllm_image, VOLUME_MOUNT, WEIGHTS_MOUNT

MODEL_NAME = "Qwen/Qwen3-8B"
MODEL_DIR = f"{WEIGHTS_MOUNT}/qwen3-8b"

SYSTEM_PROMPT = """You are Alethia, an AI-powered Chicago business intelligence analyst.
You analyze real-time data from 7+ pipelines covering permits, inspections, licenses,
news, politics, demographics, and community sentiment across 77 Chicago neighborhoods.

When answering questions:
- Cite specific data points and sources
- Compare neighborhoods when relevant
- Quantify risks and opportunities on a 1-10 scale
- Be direct and actionable — the user is making a real business decision
- Reference specific regulations, permit requirements, and zoning rules when applicable"""


@app.cls(
    gpu="H100",
    image=vllm_image,
    volumes={VOLUME_MOUNT: volume, WEIGHTS_MOUNT: weights_volume},
    secrets=[modal.Secret.from_name("alethia-secrets")],
    scaledown_window=300,
    timeout=600,
)
@modal.concurrent(max_inputs=20)
class AlethiaLLM:
    """Self-hosted Qwen3-8B inference engine on H100 GPU."""

    @modal.enter()
    def load_model(self):
        from vllm import AsyncLLMEngine, AsyncEngineArgs

        args = AsyncEngineArgs(
            model=MODEL_NAME,
            tensor_parallel_size=1,
            max_model_len=8192,
            gpu_memory_utilization=0.90,
            download_dir=MODEL_DIR,
        )
        self.engine = AsyncLLMEngine.from_engine_args(args)

    @modal.method()
    async def generate(self, messages: list[dict], max_tokens: int = 2048, temperature: float = 0.7) -> str:
        """Non-streaming generation. Returns complete response text."""
        from vllm import SamplingParams

        prompt = self._build_prompt(messages)
        params = SamplingParams(
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=0.9,
        )

        request_id = str(uuid.uuid4())
        results_generator = self.engine.generate(prompt, params, request_id)

        final_output = None
        async for output in results_generator:
            final_output = output

        if final_output is None:
            return ""
        return final_output.outputs[0].text

    @modal.method()
    async def generate_stream(self, messages: list[dict], max_tokens: int = 2048, temperature: float = 0.7):
        """Streaming generation. Yields token chunks for SSE delivery."""
        from vllm import SamplingParams

        prompt = self._build_prompt(messages)
        params = SamplingParams(
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=0.9,
        )

        request_id = str(uuid.uuid4())
        results_generator = self.engine.generate(prompt, params, request_id)

        prev_len = 0
        async for output in results_generator:
            new_text = output.outputs[0].text[prev_len:]
            prev_len = len(output.outputs[0].text)
            if new_text:
                yield new_text

    def _build_prompt(self, messages: list[dict]) -> str:
        """Build a chat-format prompt from message list."""
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"<|im_start|>system\n{content}<|im_end|>")
            elif role == "user":
                parts.append(f"<|im_start|>user\n{content}<|im_end|>")
            elif role == "assistant":
                parts.append(f"<|im_start|>assistant\n{content}<|im_end|>")
        parts.append("<|im_start|>assistant\n")
        return "\n".join(parts)


@app.function(image=vllm_image, volumes={WEIGHTS_MOUNT: weights_volume}, timeout=1200)
def download_model():
    """Pre-download model weights to volume to avoid cold start delays."""
    from huggingface_hub import snapshot_download

    snapshot_download(
        MODEL_NAME,
        local_dir=MODEL_DIR,
    )
    weights_volume.commit()
    print(f"Model {MODEL_NAME} downloaded to {MODEL_DIR}")
