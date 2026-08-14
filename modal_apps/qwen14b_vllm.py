"""Serve Qwen 14B with vLLM on Modal as an OpenAI-compatible API."""

from __future__ import annotations

import json
from typing import Any

import aiohttp
import modal

APP_NAME = "travel-agent-qwen14b-parser"
MODEL_NAME = "Qwen/Qwen2.5-14B-Instruct"
SERVED_MODEL_NAME = "qwen14b-parser"
VLLM_PORT = 8000
MINUTES = 60

hf_cache_volume = modal.Volume.from_name("travel-agent-huggingface-cache", create_if_missing=True)
vllm_cache_volume = modal.Volume.from_name("travel-agent-vllm-cache", create_if_missing=True)

vllm_image = (
    modal.Image.from_registry("nvidia/cuda:12.9.0-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .uv_pip_install(
        "vllm==0.21.0",
        "huggingface_hub[hf_xet]",
        "aiohttp",
    )
    .env(
        {
            "HF_XET_HIGH_PERFORMANCE": "1",
            "VLLM_LOG_STATS_INTERVAL": "30",
        }
    )
)

app = modal.App(APP_NAME)


@app.server(
    image=vllm_image,
    gpu="L40S:1",
    scaledown_window=20 * MINUTES,
    startup_timeout=20 * MINUTES,
    volumes={
        "/root/.cache/huggingface": hf_cache_volume,
        "/root/.cache/vllm": vllm_cache_volume,
    },
    port=VLLM_PORT,
    target_concurrency=32,
    unauthenticated=True,
)
class Server:
    @modal.enter()
    def start(self):
        import subprocess

        cmd = [
            "vllm",
            "serve",
            MODEL_NAME,
            "--served-model-name",
            MODEL_NAME,
            SERVED_MODEL_NAME,
            "--host",
            "0.0.0.0",
            "--port",
            str(VLLM_PORT),
            "--dtype",
            "bfloat16",
            "--max-model-len",
            "8192",
            "--gpu-memory-utilization",
            "0.90",
            "--tensor-parallel-size",
            "1",
            "--trust-remote-code",
            "--uvicorn-log-level",
            "info",
        ]
        print("Starting vLLM:", " ".join(cmd))
        self.process = subprocess.Popen(cmd)

    @modal.exit()
    def stop(self):
        self.process.terminate()


async def wait_for_health(session: aiohttp.ClientSession, timeout_seconds: int) -> None:
    import asyncio
    import time

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            async with session.get("/health", timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    return
        except Exception:
            pass
        await asyncio.sleep(5)
    raise TimeoutError("Timed out waiting for vLLM /health.")


async def send_chat(session: aiohttp.ClientSession, messages: list[dict[str, str]]) -> dict[str, Any]:
    payload = {
        "model": SERVED_MODEL_NAME,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 400,
        "response_format": {"type": "json_object"},
    }
    async with session.post("/v1/chat/completions", json=payload) as resp:
        body = await resp.text()
        resp.raise_for_status()
        return json.loads(body)


@app.local_entrypoint()
async def test(content: str = "Tìm rooftop bar đẹp ở Đà Nẵng"):
    url = await Server.get_url.aio()
    print(f"Qwen vLLM URL: {url}")
    print(f"Use this base URL locally: {url}/v1")

    system_prompt = (
        "Return only valid JSON with keys language, locations, regions, category, "
        "topic, entity_type, content_type, content_type_required, confidence."
    )
    async with aiohttp.ClientSession(base_url=url) as session:
        print("Waiting for /health ...")
        await wait_for_health(session, timeout_seconds=20 * MINUTES)
        response = await send_chat(
            session,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
        )
    print(json.dumps(response, ensure_ascii=False, indent=2))
