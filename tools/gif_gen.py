"""
GIF generation tool.

There's no confirmed free-hosted text-to-video/GIF model on NVIDIA NIM as of
this writing — image_gen only produces stills. This tool works around that by
generating several still frames with progressively-varied prompts (each one
nudging the scene forward) and stitching them into an animated GIF with
Pillow.

Caveat worth knowing: each frame is generated independently by a still-image
model, so motion won't be as smooth/coherent as a real video model — it's an
approximation, best for simple looping animations (a character waving, a
scene subtly shifting) rather than complex continuous motion.
"""
import io
import asyncio
from PIL import Image

from tools.image_gen import generate_image

DEFAULT_FRAMES = 4
DEFAULT_FRAME_DURATION_MS = 300


async def generate_gif(prompt: str, frames: int = DEFAULT_FRAMES) -> bytes:
    frames = max(2, min(frames, 8))  # keep it sane: 2-8 frames

    frame_prompts = [
        f"{prompt}, animation frame {i + 1} of {frames}, consistent character and style, slight motion progression"
        for i in range(frames)
    ]

    images = []
    for fp in frame_prompts:
        png_bytes = await generate_image(fp)
        images.append(png_bytes)
    return await asyncio.to_thread(_encode_frames, images)


def _encode_frames(frames):
    images = []
    for data in frames:
        with Image.open(io.BytesIO(data)) as image:
            images.append(image.convert("RGB"))

    # Normalize all frames to the same size (use the first frame's size)
    base_size = images[0].size
    images = [img.resize(base_size) for img in images]

    buf = io.BytesIO()
    images[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=images[1:],
        duration=DEFAULT_FRAME_DURATION_MS,
        loop=0,
    )
    return buf.getvalue()


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "generate_gif",
        "description": (
            "Generate a short looping animated GIF from a text description. "
            "Built from multiple AI-generated frames stitched together, so it "
            "works best for simple animations (a character waving, an object "
            "spinning, a subtle scene change) rather than complex motion."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Description of the animation/scene to generate.",
                },
                "frames": {
                    "type": "integer",
                    "description": "Number of frames (2-8, default 4). More frames = smoother but slower.",
                },
            },
            "required": ["prompt"],
        },
    },
}
