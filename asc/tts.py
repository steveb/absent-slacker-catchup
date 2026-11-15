"""Render a chat summary as speech with Piper."""

from __future__ import annotations

import logging
import re
import wave
from pathlib import Path

LOG = logging.getLogger(__name__)


class TtsError(RuntimeError):
    """Raised when speech synthesis fails."""


def clean_for_speech(summary: str) -> str:
    """Turn a markdown summary into something that reads well aloud."""
    text = summary
    # Replace asterisk bullets with hyphens, then drop remaining asterisks.
    text = re.sub(r"^\* ", "- ", text, flags=re.DOTALL)
    text = text.replace("*", "")
    # Headings do not help the listener.
    text = text.replace("#", "")
    # Replace any other punctuation with a full stop.
    return re.sub(r"[^\w\s,] ", ". ", text, flags=re.DOTALL)


def synthesize(text: str, output: Path, model: Path) -> Path:
    """Write ``text`` to ``output`` as a WAV file using the Piper voice model."""
    try:
        from piper import PiperVoice, SynthesisConfig
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise TtsError("piper-tts is not installed") from exc

    if not model.exists():
        raise TtsError(
            f"voice model {model} not found; set tts.model or download it into "
            f"{Path('~/.local/share/asc/models').expanduser()}"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    config = SynthesisConfig(noise_w_scale=1.0)
    try:
        voice = PiperVoice.load(str(model))
        with wave.open(str(output), "wb") as wav_file:
            voice.synthesize_wav(text, wav_file, syn_config=config)
    except Exception as exc:
        raise TtsError(f"speech synthesis failed: {exc}") from exc
    LOG.debug("wrote %s", output)
    return output
