"""NOLAN background removal — turn any image into a transparent RGBA cutout.

Wraps `rembg` (ONNX, CPU-capable, runs off the GPU lock so it never queues
behind ComfyUI/OmniVoice). Three model families are exposed:

    isnet     -> isnet-general-use   (default; fast, strong general cutouts)
    birefnet  -> birefnet-general    (best edges/hair, heavier/slower)
    u2net     -> u2net               (classic baseline)

    from nolan.cutout import remove_background, cutout_file

    img = remove_background("photo.jpg")                 # PIL RGBA, isnet
    img = remove_background("hair.jpg", model="birefnet") # finer matting
    out = cutout_file("frame.png", model="isnet")         # writes frame.cutout.png

First use of a model downloads its weights once (rembg cache, ~/.u2net or
$U2NET_HOME). Sessions are cached per-model for the life of the process.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Union

# Friendly name -> rembg model id. Extra models accepted too (see resolve()).
MODELS = {
    "isnet": "isnet-general-use",
    "birefnet": "birefnet-general",
    "u2net": "u2net",
    # handy extras, opt-in by name
    "u2netp": "u2netp",
    "isnet-anime": "isnet-anime",
    "birefnet-portrait": "birefnet-portrait",
    "silueta": "silueta",
}
DEFAULT_MODEL = "isnet"

_SESSIONS: dict = {}


def resolve(model: str) -> str:
    """Map a friendly alias to a rembg model id (pass-through if already an id)."""
    if not model:
        return MODELS[DEFAULT_MODEL]
    key = model.strip().lower()
    if key in MODELS:
        return MODELS[key]
    # allow raw rembg ids (e.g. "birefnet-massive") without gatekeeping
    return model


def get_session(model: str = DEFAULT_MODEL):
    """Return a cached rembg session for `model` (lazy import + lazy download)."""
    name = resolve(model)
    sess = _SESSIONS.get(name)
    if sess is None:
        from rembg import new_session  # heavy import, deferred

        sess = new_session(name)
        _SESSIONS[name] = sess
    return sess


def _to_pil(image):
    from PIL import Image

    if isinstance(image, Image.Image):
        return image
    if isinstance(image, (bytes, bytearray)):
        return Image.open(BytesIO(bytes(image)))
    return Image.open(Path(image))  # str / Path


def remove_background(
    image: Union[str, Path, bytes, "object"],
    model: str = DEFAULT_MODEL,
    *,
    alpha_matting: bool = False,
    alpha_matting_foreground_threshold: int = 240,
    alpha_matting_background_threshold: int = 10,
    alpha_matting_erode_size: int = 10,
    post_process_mask: bool = True,
    only_mask: bool = False,
):
    """Remove the background; return a PIL RGBA image (or L mask if only_mask).

    alpha_matting refines soft/hairy edges at extra cost — worth it on portraits
    with the birefnet model; leave off for crisp-edged objects/logos.
    """
    from rembg import remove  # heavy import, deferred

    src = _to_pil(image).convert("RGB")
    return remove(
        src,
        session=get_session(model),
        alpha_matting=alpha_matting,
        alpha_matting_foreground_threshold=alpha_matting_foreground_threshold,
        alpha_matting_background_threshold=alpha_matting_background_threshold,
        alpha_matting_erode_size=alpha_matting_erode_size,
        post_process_mask=post_process_mask,
        only_mask=only_mask,
    )


def cutout_file(
    src: Union[str, Path],
    dst: Union[str, Path, None] = None,
    model: str = DEFAULT_MODEL,
    **kwargs,
) -> Path:
    """Cut out `src` and write a transparent PNG. Returns the output path.

    Default output is ``<src-stem>.cutout.png`` beside the source.
    """
    src = Path(src)
    out = Path(dst) if dst else src.with_suffix("").with_name(src.stem + ".cutout.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    result = remove_background(src, model=model, **kwargs)
    result.save(out)  # PNG keeps the alpha channel
    return out
