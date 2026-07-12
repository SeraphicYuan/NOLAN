"""Generate-from-source asset prep — the deterministic half of the explainer's
`generate-from-source` ingest mode (registry.json `types[].ingest`).

A source paper/article becomes the chapter spec's INPUT assets:
  - figure_catalog / extract_figure : lift empirical figures for PaperFigure   [PIL]
  - synthesize_segments             : narration wavs via OmniVoice (cloning)    [nolan.tts]
  - word_timestamps                 : per-wav Whisper word timings → wordsCache [nolan.whisper]

The agent authors the chapter spec BETWEEN figure_catalog and synthesize (that's the
skill part — pick figures, write the script, place anchors); `ingest_explainer` then
assembles spec + these assets into the render job. In-process ports of the former
web-video-lab probes (extract_figure.py, synth_omnivoice.py, word_timestamps*.py); heavy
deps (tts/whisper/PIL) are imported lazily so importing this module stays cheap.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import urlopen

from .ingest import _localize


# ───────────────────────────────── figures (PIL, no model) ─────────────────────────────────
def _mineru_figures(md: str) -> list[dict]:
    """Catalog every figure in a MinerU content.md (image ref then a 'Figure N: caption'
    and optional 'Source:' line). Doc-ordered {figure, image, caption, source} — what a
    chapter agent reads to choose which empirical figures to lift."""
    lines = md.splitlines()
    figs: list[dict] = []
    for i, ln in enumerate(lines):
        m = re.match(r"!\[\]\(([^)]+)\)", ln.strip())
        if not m:
            continue
        img = m.group(1)
        cap, num, src = "", None, ""
        for j in range(i + 1, min(i + 4, len(lines))):
            t = lines[j].strip()
            cm = re.match(r"Figure\s*(\d+)\s*:\s*(.*)", t)
            if cm:
                num, cap = int(cm.group(1)), cm.group(2).strip()
            elif t.startswith("Source:"):
                src = t[len("Source:"):].strip()
            elif cm is None and not cap and t:
                break
        if num is not None:
            figs.append({"figure": num, "image": img, "caption": cap, "source": src})
    return figs


def _html_figures(html: str) -> list[dict]:
    figs: list[dict] = []
    for m in re.finditer(r'<img[^>]+src="([^"]+)"', html):
        cap = re.search(r"Figure\s*(\d+)\s*:\s*([^<]*)", html[m.start():m.start() + 2000])
        if cap:
            figs.append({"figure": int(cap.group(1)), "image": m.group(1),
                         "caption": re.sub(r"\s+", " ", cap.group(2)).strip()})
    return figs


def figure_catalog(source, *, is_html: bool = False) -> list[dict]:
    """Catalog the figures in a MinerU content.md (default) or arXiv HTML (is_html=True)."""
    text = Path(_localize(source)).read_text(encoding="utf-8")
    return _html_figures(text) if is_html else _mineru_figures(text)


def _figure_img_src(html: str, fig_num: int) -> str:
    for m in re.finditer(r'<img[^>]+src="([^"]+)"', html):
        cap = re.search(r"Figure\s*(\d+)\s*:", html[m.start():m.start() + 2000])
        if cap and int(cap.group(1)) == fig_num:
            return m.group(1)
    raise ValueError(f"no <img> found for Figure {fig_num}")


def _load_img(src: str, base_url, html_dir: Path):
    from PIL import Image
    if src.startswith("http"):
        return Image.open(urlopen(src)).convert("RGBA")
    if base_url:
        return Image.open(urlopen(urljoin(base_url, src))).convert("RGBA")
    return Image.open(html_dir / src).convert("RGBA")


def _trim(im, pad: int = 12, thresh: int = 250):
    """Crop near-white margins, then pad with transparent pixels."""
    from PIL import Image, ImageChops
    rgb = im.convert("RGB")
    bg = Image.new("RGB", rgb.size, (255, 255, 255))
    diff = ImageChops.difference(rgb, bg).convert("L")
    bbox = diff.point(lambda p: 255 if p > (255 - thresh) else 0).getbbox()
    if bbox:
        im = im.crop(bbox)
    out = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
    out.paste(im, (pad, pad))
    return out


def _matte(im, thresh: int = 244):
    """Set near-white pixels transparent. NOTE: corrupts light-ink/grayscale figures on dark
    themes (the invisible-ink trap) — reserve for figures with their own dark/colored fill."""
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if r >= thresh and g >= thresh and b >= thresh:
                px[x, y] = (r, g, b, 0)
    return im


def extract_figure(source, figure: int, out, *, is_html: bool = False,
                   base_url=None, matte: bool = False) -> Path:
    """Lift one figure's image, trim margins, optionally matte near-white -> transparent.
    MinerU content.md (default) or arXiv HTML (is_html=True). Returns the written png path."""
    src_path = Path(_localize(source))
    text = src_path.read_text(encoding="utf-8")
    if is_html:
        rel = _figure_img_src(text, figure)
        im = _trim(_load_img(rel, base_url, src_path.parent))
    else:
        rel = next((f["image"] for f in _mineru_figures(text) if f["figure"] == figure), None)
        if rel is None:
            raise ValueError(f"no figure {figure} in markdown")
        from PIL import Image
        im = _trim(Image.open(src_path.parent / rel).convert("RGBA"))
    if matte:
        im = _matte(im)
    out_p = Path(_localize(out))
    out_p.parent.mkdir(parents=True, exist_ok=True)
    im.save(out_p)
    return out_p


# ───────────────────────────────── narration (nolan.tts OmniVoice) ─────────────────────────
def synthesize_segments(segments, out_dir, *, ref=None, num_step=None, quiet: bool = False) -> dict:
    """Synthesize each segment's narration with NOLAN's OmniVoice (local voice cloning).

    `segments` is a list (or a path to JSON) of {chapter, step, text}; wavs are written as
    <chapter>_<step>.wav into out_dir. Returns {"<chapter>_<step>": wav_path}. With `ref`,
    clones that reference voice. This produces the spec's `wav` assets.
    """
    from nolan.config import load_config
    from nolan.tts import create_tts_provider

    segs = (segments if isinstance(segments, list)
            else json.loads(Path(_localize(segments)).read_text(encoding="utf-8")))
    ref_p = str(Path(_localize(ref)).resolve()) if ref else None
    items = [{"id": f"{s['chapter']}_{s['step']}", "text": s["text"],
              **({"ref_audio": ref_p} if ref_p else {})} for s in segs]

    cfg = load_config()
    provider = create_tts_provider(cfg.tts)            # OmniVoiceTTS (dedicated CUDA env)
    out_p = Path(_localize(out_dir))
    out_p.mkdir(parents=True, exist_ok=True)
    steps = num_step if num_step is not None else getattr(cfg.tts.omnivoice, "num_step", 32)
    if not quiet:
        print(f"synthesizing {len(items)} segments via OmniVoice (ref={'yes' if ref_p else 'auto'}) …")
    produced = provider.synthesize_batch(items, out_p, num_step=steps)
    if not quiet:
        ok = sum(1 for it in items if produced.get(it["id"]) and Path(produced[it["id"]]).exists())
        print(f"done: {ok}/{len(items)} wavs in {out_p}")
    return produced


# ───────────────────────────────── word timings (nolan.whisper) ────────────────────────────
def word_timestamps(wavs, out_path=None, *, model_size: str = "base", device: str = "cpu",
                    compute_type: str = "int8", quiet: bool = False) -> dict:
    """Per-word Whisper timings for one wav or many. Returns {wav_stem: [{word,start,end}, …]}
    — exactly the `wordsCache` shape ingest_explainer reads. Loads whisper once for the batch.
    CPU/int8 by default (avoids a missing-cuBLAS issue in this env; fine for short clips)."""
    from nolan.whisper import WhisperConfig, WhisperTranscriber

    paths = [wavs] if isinstance(wavs, (str, Path)) else list(wavs)
    tr = WhisperTranscriber(WhisperConfig(model_size=model_size, device=device, compute_type=compute_type))
    res: dict = {}
    for w in paths:
        wp = Path(_localize(w))
        words = tr.transcribe_words(wp)
        # emit BOTH `word` (NOLAN convention) and `text` (what captions.mjs reads) so the audio_meta
        # word contract is uniform across the NOLAN-VO and media-use producers (was a silent caption skip)
        res[wp.stem] = [{"word": x.word, "text": x.word, "start": round(x.start, 3), "end": round(x.end, 3)} for x in words]
        if not quiet:
            print(f"  {wp.stem}: {len(res[wp.stem])} words")
    if out_path:
        op = Path(_localize(out_path))
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(json.dumps(res, indent=2), encoding="utf-8")
        if not quiet:
            print(f"-> {op}")
    return res
