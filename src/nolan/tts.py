"""Text-to-speech / voice-cloning providers for NOLAN.

Mirrors the create_text_llm / create_vision_provider factory pattern. The only
engine today is OmniVoice (local, zero-shot voice cloning), which runs in a
dedicated CUDA conda env (see scripts/setup_omnivoice.ps1) and is invoked as a
batch subprocess so its heavy torch stack never enters the lean `nolan` env and
its VRAM is released when the job finishes.

GPU serialization is the caller's job: the voiceover worker holds the shared
``get_gpu_lock()`` while calling ``synthesize_batch`` so OmniVoice and ComfyUI
never run at the same time. Provider methods here are plain synchronous calls.
"""

from __future__ import annotations

import json
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional


class TtsProvider(ABC):
    """A speech synthesizer. ``synthesize_batch`` is the primary entry point."""

    sample_rate: int = 24000

    @abstractmethod
    def synthesize_batch(self, items: List[dict], out_dir: Path,
                         num_step: Optional[int] = None) -> Dict[str, Path]:
        """Synthesize many utterances at once (one model load).

        Args:
            items: list of dicts, each with keys:
                id (str, required), text (str, required),
                ref_audio (str path, optional — voice clone reference),
                ref_text (str, optional — ref transcript; auto if omitted),
                language_id / speed / instruct (optional).
            out_dir: directory to write ``<id>.wav`` files into.

        Returns:
            {id: wav_path} for every successfully synthesized item.
        """

    def synthesize(self, text: str, out_path: Path, ref_audio: Optional[str] = None,
                   ref_text: Optional[str] = None, num_step: Optional[int] = None, **kw) -> Path:
        """Convenience single-utterance wrapper around ``synthesize_batch``."""
        out_path = Path(out_path)
        item = {"id": out_path.stem, "text": text}
        if ref_audio:
            item["ref_audio"] = str(ref_audio)
        if ref_text:
            item["ref_text"] = ref_text
        item.update({k: v for k, v in kw.items() if v is not None})
        produced = self.synthesize_batch([item], out_path.parent, num_step=num_step)
        wav = produced.get(out_path.stem)
        if not wav:
            raise RuntimeError("TTS produced no audio")
        if wav != out_path and out_path.suffix.lower() == ".wav":
            wav.replace(out_path)
            return out_path
        return wav


class OmniVoiceTTS(TtsProvider):
    """OmniVoice via the dedicated env's ``omnivoice-infer-batch`` console script."""

    def __init__(self, cfg):
        self.cfg = cfg
        if not cfg.env_python or not Path(cfg.env_python).exists():
            raise RuntimeError(
                "tts.omnivoice.env_python is not set or missing. Run "
                "scripts/setup_omnivoice.ps1 and set it in nolan.yaml "
                "(e.g. D:\\env\\omnivoice\\python.exe)."
            )

    def _infer_batch_cmd(self) -> list:
        """Locate the omnivoice-infer-batch console entry in the dedicated env."""
        p = Path(self.cfg.env_python)
        candidates = [
            p.parent / "Scripts" / "omnivoice-infer-batch.exe",  # Windows
            p.parent / "bin" / "omnivoice-infer-batch",          # POSIX
            p.parent / "omnivoice-infer-batch",
        ]
        for c in candidates:
            if c.exists():
                return [str(c)]
        # Fallback: run via the module (entry-point script imports this).
        return [str(p), "-m", "omnivoice.bin.omnivoice_infer_batch"]

    def synthesize_batch(self, items: List[dict], out_dir: Path,
                         num_step: Optional[int] = None) -> Dict[str, Path]:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        if not items:
            return {}

        jsonl = out_dir / "_batch.jsonl"
        with jsonl.open("w", encoding="utf-8") as f:
            for it in items:
                line = {"id": it["id"], "text": it["text"]}
                for k in ("ref_audio", "ref_text", "instruct", "language_id", "duration", "speed"):
                    if it.get(k) is not None:
                        line[k] = it[k]
                f.write(json.dumps(line, ensure_ascii=False) + "\n")

        cmd = self._infer_batch_cmd() + [
            "--model", self.cfg.model,
            "--test_list", str(jsonl),
            "--res_dir", str(out_dir),
            "--num_step", str(num_step if num_step is not None else self.cfg.num_step),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(f"omnivoice-infer-batch failed: {err[:800] or 'unknown error'}")

        produced: Dict[str, Path] = {}
        for it in items:
            wav = out_dir / f"{it['id']}.wav"
            if not wav.exists():
                matches = sorted(out_dir.glob(f"{it['id']}*.wav"))
                wav = matches[0] if matches else None
            if wav and wav.exists():
                produced[it["id"]] = wav
        return produced


class CosyVoiceTTS(TtsProvider):
    """CosyVoice 3.0 in its own conda env, invoked via the standalone
    ``tts_cosyvoice_runner.py`` (which handles 16 kHz refs, the ``<|endofprompt|>`` prompt
    structure, instruct2 clone+emotion, and float32→PCM16 output). Same item schema as
    OmniVoiceTTS, so the pipeline is engine-agnostic."""

    sample_rate = 24000

    def __init__(self, cfg):
        self.cfg = cfg   # CosyVoiceConfig

    def synthesize_batch(self, items: List[dict], out_dir: Path,
                         num_step: Optional[int] = None) -> Dict[str, Path]:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        if not items:
            return {}
        jsonl = out_dir / "_cv_batch.jsonl"
        with jsonl.open("w", encoding="utf-8") as f:
            for it in items:
                line = {"id": it["id"], "text": it["text"]}
                for k in ("ref_audio", "ref_text", "instruct", "speed"):
                    if it.get(k) is not None:
                        line[k] = it[k]
                f.write(json.dumps(line, ensure_ascii=False) + "\n")

        env_python = self.cfg.env_python or "python"
        runner = str(Path(__file__).with_name("tts_cosyvoice_runner.py"))
        cmd = [env_python, runner, "--test_list", str(jsonl), "--res_dir", str(out_dir),
               "--model_dir", self.cfg.model_dir, "--repo", self.cfg.repo_dir]
        if self.cfg.neutral_instruct:
            cmd += ["--neutral_instruct", self.cfg.neutral_instruct]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=self.cfg.repo_dir or None)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(f"cosyvoice runner failed: {err[:800] or 'unknown error'}")

        produced: Dict[str, Path] = {}
        for it in items:
            wav = out_dir / f"{it['id']}.wav"
            if wav.exists():
                produced[it["id"]] = wav
        return produced


def create_tts_provider(tts_cfg) -> TtsProvider:
    """Factory: build a TtsProvider from config.tts (mirrors create_text_llm)."""
    provider = (getattr(tts_cfg, "provider", None) or "omnivoice").lower()
    if provider == "omnivoice":
        return OmniVoiceTTS(tts_cfg.omnivoice)
    if provider == "cosyvoice3":
        return CosyVoiceTTS(tts_cfg.cosyvoice)
    raise ValueError(f"unknown tts provider: {provider!r}")
