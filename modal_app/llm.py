"""Self-hosted LLM — Qwen3-8B via vLLM on H100 GPU.

Provides streaming and non-streaming text generation for the Alethia reasoning engine.
Modal features: @modal.cls, @modal.enter, @modal.concurrent, gpu=H100, Image.run_commands()
"""
import json
import uuid

import modal

from modal_app.costs import track_cost
from modal_app.volume import app, volume, weights_volume, vllm_image, VOLUME_MOUNT, WEIGHTS_MOUNT

MODEL_NAME = "Qwen/Qwen3-8B-AWQ"
MODEL_DIR = f"{WEIGHTS_MOUNT}/Qwen3-8B-AWQ"

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
    secrets=[modal.Secret.from_name("alethia-secrets"), modal.Secret.from_name("arize-secrets")],
    scaledown_window=300,
    timeout=600,
    min_containers=1,
    enable_memory_snapshot=True,
    experimental_options={"enable_gpu_snapshot": True},
)
@modal.concurrent(max_inputs=20)
class AlethiaLLM:
    """Self-hosted Qwen3-8B inference engine on H100 GPU."""

    @modal.enter(snap=True)
    @track_cost("AlethiaLLM.load_model", "H100")
    def load_model(self):
        from modal_app.instrumentation import init_tracing, get_tracer
        init_tracing()
        self._tracer = get_tracer("alethia.llm")

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
    @track_cost("AlethiaLLM.generate", "H100")
    async def generate(self, messages: list[dict], max_tokens: int = 2048, temperature: float = 0.7) -> str:
        """Non-streaming generation. Returns complete response text."""
        from vllm import SamplingParams

        span_ctx = self._tracer.start_as_current_span("llm-generate") if self._tracer else None
        span = span_ctx.__enter__() if span_ctx else None
        try:
            if span:
                span.set_attribute("openinference.span.kind", "LLM")
                span.set_attribute("llm.model_name", MODEL_NAME)
                span.set_attribute("input.value", json.dumps(messages))

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

            result = final_output.outputs[0].text if final_output else ""
            if span:
                span.set_attribute("output.value", result)
            return result
        except Exception as e:
            if span:
                span.set_attribute("error", str(e))
            raise
        finally:
            if span_ctx:
                span_ctx.__exit__(None, None, None)

    @modal.method()
    @track_cost("AlethiaLLM.generate_stream", "H100")
    async def generate_stream(self, messages: list[dict], max_tokens: int = 2048, temperature: float = 0.7):
        """Streaming generation. Yields token chunks for SSE delivery."""
        from vllm import SamplingParams

        span_ctx = self._tracer.start_as_current_span("llm-generate-stream") if self._tracer else None
        span = span_ctx.__enter__() if span_ctx else None
        try:
            if span:
                span.set_attribute("openinference.span.kind", "LLM")
                span.set_attribute("llm.model_name", MODEL_NAME)
                span.set_attribute("input.value", json.dumps(messages))

            prompt = self._build_prompt(messages)
            params = SamplingParams(
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=0.9,
            )

            request_id = str(uuid.uuid4())
            results_generator = self.engine.generate(prompt, params, request_id)

            full_output = ""
            prev_len = 0
            async for output in results_generator:
                new_text = output.outputs[0].text[prev_len:]
                prev_len = len(output.outputs[0].text)
                if new_text:
                    full_output += new_text
                    yield new_text

            if span:
                span.set_attribute("output.value", full_output)
        except Exception as e:
            if span:
                span.set_attribute("error", str(e))
            raise
        finally:
            if span_ctx:
                span_ctx.__exit__(None, None, None)

    @modal.method()
    def gpu_metrics(self) -> dict:
        """Live GPU metrics via nvidia-smi."""
        import subprocess
        from datetime import datetime, timezone
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw,power.limit,name",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return {"status": "error"}
            vals = [v.strip() for v in result.stdout.strip().split(",")]
            return {
                "status": "active",
                "gpu_utilization": int(vals[0]),
                "memory_utilization": int(vals[1]),
                "memory_used_mb": int(vals[2]),
                "memory_total_mb": int(vals[3]),
                "temperature_c": int(vals[4]),
                "power_draw_w": int(float(vals[5])),
                "power_limit_w": int(float(vals[6])),
                "gpu_name": vals[7],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

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
