"""Voice library for NOLAN TTS — saved reference voices for cloning.

A *voice* is a short reference clip (3-10s) + optional transcript that OmniVoice
clones. Voices come from an uploaded audio file or from a saved Clip's audio
(reusing the Clips feature). File-backed, like the script-style + clip libraries:

    voices/<id>/
    ├── sample.wav     # mono 24 kHz reference clip
    └── meta.json      # id, name, ref_text, source, created_at
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_ROOT = Path("voices")


def _slug(text: str, fallback: str = "voice") -> str:
    s = re.sub(r"[^\w\-]", "", re.sub(r"[\s_]+", "-", (text or "").lower()))
    return re.sub(r"-+", "-", s).strip("-") or fallback


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


class VoiceLibrary:
    """File-backed manager for cloneable reference voices."""

    def __init__(self, root: Path = DEFAULT_ROOT):
        self.root = Path(root)

    # --- paths -----------------------------------------------------------------
    def _dir(self, voice_id: str) -> Path:
        return self.root / voice_id

    def sample_path(self, voice_id: str) -> Path:
        return self._dir(voice_id) / "sample.wav"

    def _meta_path(self, voice_id: str) -> Path:
        return self._dir(voice_id) / "meta.json"

    def exists(self, voice_id: str) -> bool:
        return self._meta_path(voice_id).exists()

    # --- helpers ---------------------------------------------------------------
    def _new_id(self, name: str) -> str:
        base = _slug(name)
        vid, n = base, 2
        while self._dir(vid).exists():
            vid = f"{base}-{n}"
            n += 1
        return vid

    def _extract(self, cmd_in: list, out_wav: Path) -> None:
        """Run ffmpeg to write a mono 24 kHz wav reference clip."""
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        cmd = [_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", *cmd_in,
               "-vn", "-ac", "1", "-ar", "24000", str(out_wav)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not out_wav.exists():
            raise RuntimeError(f"ffmpeg failed to extract reference audio: "
                               f"{(proc.stderr or '').strip()[:300]}")

    def _write_meta(self, voice_id: str, name: str, ref_text: Optional[str],
                    source: str, source_ref: Optional[str]) -> Dict[str, Any]:
        meta = {
            "id": voice_id,
            "name": name,
            "ref_text": ref_text or None,
            "source": source,           # upload | clip
            "source_ref": source_ref,   # filename or clip id
            "created_at": datetime.now().isoformat(),
        }
        self._meta_path(voice_id).write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        return meta

    # --- create ----------------------------------------------------------------
    def create_from_audio(self, name: str, src_audio: Path, ref_text: Optional[str] = None,
                          source: str = "upload", source_ref: Optional[str] = None) -> Dict[str, Any]:
        """Create a voice from an existing audio file (any format)."""
        vid = self._new_id(name)
        self._extract(["-i", str(src_audio)], self.sample_path(vid))
        return self._write_meta(vid, name, ref_text, source, source_ref or Path(src_audio).name)

    def create_from_clip(self, name: str, video_path: str, start: float, end: float,
                         ref_text: Optional[str] = None, clip_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a voice from a saved Clip's audio (source video + in/out)."""
        duration = float(end) - float(start)
        if duration <= 0:
            raise ValueError("clip end must be after start")
        vid = self._new_id(name)
        self._extract(["-ss", str(start), "-i", str(video_path), "-t", f"{duration:.3f}"],
                      self.sample_path(vid))
        return self._write_meta(vid, name, ref_text, "clip", clip_id or Path(video_path).name)

    # --- read / delete ---------------------------------------------------------
    def get(self, voice_id: str) -> Optional[Dict[str, Any]]:
        if not self.exists(voice_id):
            return None
        meta = json.loads(self._meta_path(voice_id).read_text(encoding="utf-8"))
        meta["has_sample"] = self.sample_path(voice_id).exists()
        return meta

    def list(self) -> List[Dict[str, Any]]:
        out = []
        if not self.root.exists():
            return out
        for d in sorted(self.root.iterdir()):
            if (d / "meta.json").exists():
                try:
                    m = json.loads((d / "meta.json").read_text(encoding="utf-8"))
                    out.append({"id": m["id"], "name": m.get("name", m["id"]),
                                "source": m.get("source"), "has_ref_text": bool(m.get("ref_text")),
                                "created_at": m.get("created_at")})
                except Exception:
                    continue
        out.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return out

    # --- ephemeral samples (TTS Studio: use-once references) -------------------
    def temp_sample_path(self, token: str) -> Path:
        return self.root / "_tmp" / f"{token}.wav"

    def make_temp_sample(self, token: str, *, src_audio: Optional[Path] = None,
                         video_path: Optional[str] = None, start: Optional[float] = None,
                         end: Optional[float] = None) -> Path:
        """Extract a one-off reference clip (not added to the library) for cloning."""
        out = self.temp_sample_path(token)
        if src_audio is not None:
            self._extract(["-i", str(src_audio)], out)
        elif video_path is not None:
            duration = float(end) - float(start)
            if duration <= 0:
                raise ValueError("end must be after start")
            self._extract(["-ss", str(start), "-i", str(video_path), "-t", f"{duration:.3f}"], out)
        else:
            raise ValueError("make_temp_sample needs src_audio or video_path+start+end")
        return out

    def promote_temp(self, token: str, name: str, ref_text: Optional[str] = None) -> Dict[str, Any]:
        """Save an ephemeral sample into the library as a named voice."""
        tmp = self.temp_sample_path(token)
        if not tmp.exists():
            raise FileNotFoundError(f"sample not found: {token}")
        return self.create_from_audio(name, tmp, ref_text=ref_text,
                                      source="upload", source_ref=f"sample:{token}")

    def delete(self, voice_id: str) -> bool:
        d = self._dir(voice_id)
        if not d.exists():
            return False
        import shutil
        shutil.rmtree(d, ignore_errors=True)
        return True
