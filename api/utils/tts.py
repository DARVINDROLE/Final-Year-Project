"""
TTS (Text-to-Speech) utility for the Smart Doorbell Action Agent.

Supports two modes:
  1. pyttsx3  — cross-platform, works on Windows/Linux/Pi (recommended dev)
  2. espeak   — lightweight CLI tool available on Raspberry Pi / Linux

The helper generates an audio file (WAV) at `data/tts/{session_id}.wav`
and optionally plays it through the local speaker.

All text is sanitized before TTS to prevent shell injection or malformed input.
"""

from __future__ import annotations

import importlib
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Maximum TTS text length (characters) — prevents extremely long speech
MAX_TTS_LENGTH = 240


# ──────────────────────────────────────────────────────────────
# Text sanitization (security-critical)
# ──────────────────────────────────────────────────────────────

def sanitize_tts_text(text: str) -> str:
    """Remove control characters, limit length, and escape quotes for safe TTS."""
    safe = "".join(ch for ch in text if ch.isprintable())
    safe = safe.replace('"', "'")
    return safe[:MAX_TTS_LENGTH]


# ──────────────────────────────────────────────────────────────
# TTS engine abstraction
# ──────────────────────────────────────────────────────────────

def generate_tts_audio(
    text: str,
    session_id: str,
    output_dir: str = "data/tts",
    play: bool = False,
) -> str:
    """Generate TTS audio file and optionally play it.

    Returns the path to the generated WAV/text file.
    Tries pyttsx3 first, falls back to espeak, then writes text-only file.
    """
    safe_text = sanitize_tts_text(text)
    if not safe_text:
        logger.warning("Empty TTS text after sanitization for session %s", session_id)
        return ""

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Try pyttsx3 (cross-platform, works on Windows + Pi)
    wav_path = _try_pyttsx3(safe_text, session_id, out_dir, play=play)
    if wav_path:
        return wav_path

    # Try espeak (lightweight, Pi/Linux)
    wav_path = _try_espeak(safe_text, session_id, out_dir, play=play)
    if wav_path:
        return wav_path

    # Fallback: write text file only (no audio generation)
    logger.warning("No TTS engine available — writing text-only preview for %s", session_id)
    return _write_text_fallback(safe_text, session_id, out_dir)


def play_tts_text(text: str) -> bool:
    """Play TTS text through local speaker (for interactive testing).
    Returns True if playback succeeded."""
    safe_text = sanitize_tts_text(text)
    if not safe_text:
        return False

    try:
        pyttsx3 = importlib.import_module("pyttsx3")
        engine = pyttsx3.init()
        engine.setProperty("rate", 160)
        engine.setProperty("volume", 1.0)
        engine.say(safe_text)
        engine.runAndWait()
        engine.stop()
        return True
    except Exception:
        pass

    # Try espeak direct playback
    try:
        result = subprocess.run(
            ["espeak", "-v", "en", safe_text],
            check=False,
            timeout=15,
            shell=False,
            capture_output=True,
        )
        return result.returncode == 0
    except Exception:
        pass

    return False


# ──────────────────────────────────────────────────────────────
# Engine implementations
# ──────────────────────────────────────────────────────────────

def _try_pyttsx3(text: str, session_id: str, out_dir: Path, play: bool = False) -> str:
    """Generate WAV using pyttsx3. Returns file path or empty string."""
    try:
        pyttsx3 = importlib.import_module("pyttsx3")
        engine = pyttsx3.init()
        engine.setProperty("rate", 160)
        engine.setProperty("volume", 1.0)

        wav_path = out_dir / f"{session_id}.wav"

        # pyttsx3 can save to file
        engine.save_to_file(text, str(wav_path))
        engine.runAndWait()
        engine.stop()

        if wav_path.exists() and wav_path.stat().st_size > 0:
            logger.info("TTS (pyttsx3) generated: %s", wav_path)

            if play:
                _play_wav(str(wav_path))

            return str(wav_path).replace("\\", "/")

        # Some pyttsx3 backends don't support save_to_file well;
        # if file is empty, play directly and write text file instead
        if play:
            engine2 = pyttsx3.init()
            engine2.setProperty("rate", 160)
            engine2.say(text)
            engine2.runAndWait()
            engine2.stop()

        # Write text fallback alongside
        return _write_text_fallback(text, session_id, out_dir)

    except ImportError:
        logger.debug("pyttsx3 not installed")
        return ""
    except Exception as exc:
        logger.debug("pyttsx3 failed: %s", exc)
        return ""


def _try_espeak(text: str, session_id: str, out_dir: Path, play: bool = False) -> str:
    """Generate WAV using espeak CLI. Returns file path or empty string."""
    try:
        wav_path = out_dir / f"{session_id}.wav"

        # Generate WAV file with espeak (shell=False for safety)
        result = subprocess.run(
            ["espeak", "-v", "en", "-w", str(wav_path), text],
            check=False,
            timeout=10,
            shell=False,
            capture_output=True,
        )

        if result.returncode == 0 and wav_path.exists():
            logger.info("TTS (espeak) generated: %s", wav_path)

            if play:
                _play_wav(str(wav_path))

            return str(wav_path).replace("\\", "/")

        return ""

    except FileNotFoundError:
        logger.debug("espeak not found on system")
        return ""
    except Exception as exc:
        logger.debug("espeak failed: %s", exc)
        return ""


def _write_text_fallback(text: str, session_id: str, out_dir: Path) -> str:
    """Write a text-only preview file when no TTS engine is available."""
    txt_path = out_dir / f"{session_id}.txt"
    txt_path.write_text(text, encoding="utf-8")
    logger.info("TTS fallback (text): %s", txt_path)
    return str(txt_path).replace("\\", "/")


def _play_wav(wav_path: str) -> None:
    """Attempt to play a WAV file through the system speaker."""
    import platform

    system = platform.system()
    try:
        if system == "Windows":
            import winsound
            winsound.PlaySound(wav_path, winsound.SND_FILENAME)
        elif system == "Linux":
            subprocess.run(
                ["aplay", wav_path],
                check=False,
                timeout=15,
                shell=False,
                capture_output=True,
            )
        elif system == "Darwin":
            subprocess.run(
                ["afplay", wav_path],
                check=False,
                timeout=15,
                shell=False,
                capture_output=True,
            )
    except Exception as exc:
        logger.debug("WAV playback failed: %s", exc)
