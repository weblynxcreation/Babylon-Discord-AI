"""
Image generation tool. Primary path: NVIDIA NIM-hosted Stable Diffusion 3.
Falls back to Stability AI's direct API if STABILITY_API_KEY is set and
NIM image gen fails (or isn't configured).

Returns raw PNG bytes so the caller can attach them directly to a Discord
message — no temp-file juggling needed.
"""
import os
import base64
import aiohttp

NIM_IMAGE_URL_TEMPLATE = "https://ai.api.nvidia.com/v1/genai/{model}"
STABILITY_URL = "https://api.stability.ai/v2beta/stable-image/generate/sd3"


async def _generate_nim(prompt: str) -> bytes:
    api_key = os.environ.get("NVIDIA_API_KEY")
    model = os.environ.get("NVIDIA_IMAGE_MODEL", "stabilityai/stable-diffusion-3-medium")
    if not api_key:
        raise RuntimeError("NVIDIA_API_KEY is not set.")

    url = NIM_IMAGE_URL_TEMPLATE.format(model=model)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = {"prompt": prompt, "cfg_scale": 5, "aspect_ratio": "1:1", "seed": 0, "steps": 30}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload, timeout=120) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"NIM image gen failed ({resp.status}): {text[:300]}")
            data = await resp.json()
            b64_image = data.get("image") or data.get("images", [None])[0]
            if not b64_image:
                raise RuntimeError(f"NIM image gen returned no image data: {data}")
            return base64.b64decode(b64_image)


async def _generate_stability(prompt: str) -> bytes:
    api_key = os.environ.get("STABILITY_API_KEY")
    if not api_key:
        raise RuntimeError("STABILITY_API_KEY is not set.")

    headers = {"Authorization": f"Bearer {api_key}", "Accept": "image/*"}
    form = aiohttp.FormData()
    form.add_field("prompt", prompt)
    form.add_field("output_format", "png")

    async with aiohttp.ClientSession() as session:
        async with session.post(STABILITY_URL, headers=headers, data=form, timeout=120) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Stability image gen failed ({resp.status}): {text[:300]}")
            return await resp.read()


async def generate_image(prompt: str) -> bytes:
    """Try NIM first, fall back to Stability AI if configured."""
    try:
        return await _generate_nim(prompt)
    except Exception as nim_error:
        if os.environ.get("STABILITY_API_KEY"):
            return await _generate_stability(prompt)
        raise RuntimeError(f"Image generation failed and no fallback configured: {nim_error}")


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "generate_image",
        "description": "Generate an image from a text description and return it to the user.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed visual description of the image to generate.",
                }
            },
            "required": ["prompt"],
        },
    },
}
