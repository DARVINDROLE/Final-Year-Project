"""
TTS (Text-to-Speech) utility for the Smart Doorbell Action Agent.

Supports three engines (tried in priority order):
  1. edge-tts — Microsoft Edge neural voices (natural, high-quality)
  2. pyttsx3  — cross-platform offline fallback (Windows/Linux/Pi)
  3. espeak   — lightweight CLI tool available on Raspberry Pi / Linux

The helper generates an audio file at ``data/tts/{session_id}.mp3``
(or ``.wav`` for legacy engines) and optionally plays it through the
local speaker.

All text is sanitized before TTS to prevent shell injection or malformed input.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import platform
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Maximum TTS text length (characters) — prevents extremely long speech
MAX_TTS_LENGTH = 240

# Default edge-tts voice — Indian English, female, natural-sounding
EDGE_TTS_VOICE = "en-IN-NeerjaNeural"


# ──────────────────────────────────────────────────────────────
# Async helper (avoids disrupting the default event loop)
# ──────────────────────────────────────────────────────────────

def _run_async(coro):
    """Run a coroutine from sync code *without* closing the default event loop.

    Unlike ``asyncio.run()``, this uses a private event loop so that
    ``asyncio.get_event_loop()`` still works afterwards — important when
    called from within pytest or other frameworks that rely on the default loop.
    If we are already *inside* a running async loop (e.g. an ``await`` chain),
    we offload the work to a background thread to avoid deadlocks.
    """
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None

    if running is not None and running.is_running():
        # Inside an existing async context — run in a separate thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(timeout=15)

    # No running loop — use a disposable one
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


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

    Returns the path to the generated audio/text file.
    Tries edge-tts first (neural voice), falls back to pyttsx3, espeak,
    then writes text-only file.
    """
    safe_text = sanitize_tts_text(text)
    if not safe_text:
        logger.warning("Empty TTS text after sanitization for session %s", session_id)
        return ""

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Try edge-tts (Microsoft neural voices — best quality)
    audio_path = _try_edge_tts(safe_text, session_id, out_dir, play=play)
    if audio_path:
        return audio_path

    # Try pyttsx3 (cross-platform offline, works on Windows + Pi)
    audio_path = _try_pyttsx3(safe_text, session_id, out_dir, play=play)
    if audio_path:
        return audio_path

    # Try espeak (lightweight, Pi/Linux)
    audio_path = _try_espeak(safe_text, session_id, out_dir, play=play)
    if audio_path:
        return audio_path

    # Fallback: write text file only (no audio generation)
    logger.warning("No TTS engine available — writing text-only preview for %s", session_id)
    return _write_text_fallback(safe_text, session_id, out_dir)


def play_tts_text(text: str) -> bool:
    """Play TTS text through local speaker (for interactive testing).
    Returns True if playback succeeded."""
    safe_text = sanitize_tts_text(text)
    if not safe_text:
        return False

    # Try edge-tts (best quality)
    try:
        edge_tts = importlib.import_module("edge_tts")
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name

        async def _gen():
            comm = edge_tts.Communicate(safe_text, EDGE_TTS_VOICE)
            await comm.save(tmp_path)

        _run_async(_gen())
        if Path(tmp_path).exists() and Path(tmp_path).stat().st_size > 0:
            _play_audio(tmp_path)
            return True
    except Exception as exc:
        logger.debug("edge-tts playback failed: %s", exc)

    # Try pyttsx3
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

def _try_edge_tts(text: str, session_id: str, out_dir: Path, play: bool = False) -> str:
    """Generate MP3 using edge-tts (Microsoft neural voice). Returns file path or empty string."""
    try:
        edge_tts = importlib.import_module("edge_tts")
        mp3_path = out_dir / f"{session_id}.mp3"

        async def _generate():
            communicate = edge_tts.Communicate(text, EDGE_TTS_VOICE)
            await communicate.save(str(mp3_path))

        _run_async(_generate())

        if mp3_path.exists() and mp3_path.stat().st_size > 0:
            logger.info("TTS (edge-tts / %s) generated: %s", EDGE_TTS_VOICE, mp3_path)

            if play:
                _play_audio(str(mp3_path))

            return str(mp3_path).replace("\\", "/")

        return ""

    except ImportError:
        logger.debug("edge-tts not installed")
        return ""
    except Exception as exc:
        logger.debug("edge-tts failed: %s", exc)
        return ""


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
                _play_audio(str(wav_path))

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
                _play_audio(str(wav_path))

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


# ──────────────────────────────────────────────────────────────
# Audio playback (supports WAV + MP3)
# ──────────────────────────────────────────────────────────────

def _play_audio(audio_path: str) -> None:
    """Play an audio file (WAV or MP3) through the system speaker."""
    ext = Path(audio_path).suffix.lower()
    system = platform.system()

    # Try pygame first (handles WAV + MP3, cross-platform)
    try:
        pygame = importlib.import_module("pygame")
        pygame.mixer.init()
        pygame.mixer.music.load(audio_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(100)
        pygame.mixer.quit()
        return
    except Exception:
        pass

    try:
        if system == "Windows":
            if ext == ".wav":
                import winsound
                winsound.PlaySound(audio_path, winsound.SND_FILENAME)
            else:
                # MP3/other on Windows — use PowerShell MediaPlayer (.NET)
                _play_mp3_windows(audio_path)
        elif system == "Linux":
            if ext == ".wav":
                subprocess.run(
                    ["aplay", audio_path],
                    check=False, timeout=30, shell=False, capture_output=True,
                )
            else:
                # Try mpg123, then ffplay for MP3
                for cmd in [["mpg123", "-q", audio_path], ["ffplay", "-nodisp", "-autoexit", audio_path]]:
                    try:
                        r = subprocess.run(cmd, check=False, timeout=30, shell=False, capture_output=True)
                        if r.returncode == 0:
                            break
                    except FileNotFoundError:
                        continue
        elif system == "Darwin":
            subprocess.run(
                ["afplay", audio_path],
                check=False, timeout=30, shell=False, capture_output=True,
            )
    except Exception as exc:
        logger.debug("Audio playback failed: %s", exc)


def _play_mp3_windows(audio_path: str) -> None:
    """Play MP3 on Windows using PowerShell .NET MediaPlayer."""
    abs_path = str(Path(audio_path).resolve()).replace("\\", "/")
    ps_script = (
        "Add-Type -AssemblyName PresentationCore; "
        "$p = New-Object System.Windows.Media.MediaPlayer; "
        f"$p.Open([uri]'file:///{abs_path}'); "
        "Start-Sleep -Milliseconds 500; "
        "$p.Play(); "
        "while(-not $p.NaturalDuration.HasTimeSpan){Start-Sleep -Milliseconds 100}; "
        "$dur = [int]$p.NaturalDuration.TimeSpan.TotalMilliseconds + 200; "
        "Start-Sleep -Milliseconds $dur; "
        "$p.Close()"
    )
    subprocess.run(
        ["powershell", "-c", ps_script],
        check=False, timeout=30, shell=False, capture_output=True,
    )
