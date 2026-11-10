
import argparse
import re
import shutil
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

BASE = Path(__file__).resolve().parent
INPUT = BASE / "input"
OUTPUT = BASE / "output"
MODELS = BASE / "models"

MODEL = MODELS / "kokoro-v1.0.onnx"
VOICES = MODELS / "voices-v1.0.bin"

NARRATION = INPUT / "narration.wav"
TEST_AUDIO = OUTPUT / "adam_smooth_test.wav"

# ====================================
# VOICE CONFIGURATION
# ====================================

VOICE = "am_adam"
LANGUAGE = "en-us"
SPEED = 1.0

# Longer chunks reduce interruptions.
MAX_CHARS = 320

# Small natural pause between chunks.
# Previous version used 0.15 seconds.
PAUSE_SECONDS = 0.035

# Amount of silence preserved at edges.
EDGE_PADDING_MS = 25

# Short fade prevents clicks.
FADE_MS = 6

TEST_TEXT = (
    "Imagine waking up to discover that an entire "
    "company has been brought to a standstill. "
    "Computers are locked, networks are offline, "
    "and nobody knows what happens next. "
    "This is the story of how a single cyberattack "
    "can bring a billion-dollar business to its knees."
)


def latest_script():
    scripts = list(OUTPUT.glob("script_*.txt"))

    if not scripts:
        raise FileNotFoundError(
            "No script found in output."
        )

    return max(
        scripts,
        key=lambda p: p.stat().st_mtime
    )


def clean_script(text):
    text = re.sub(
        r"<think>.*?</think>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE
    )

    if "[VERIFY]" in text.upper():
        raise RuntimeError(
            "Script contains unverified claims."
        )

    text = re.sub(
        r"(?m)^\s*#{1,6}\s*",
        "",
        text
    )

    text = text.replace("**", "")
    text = text.replace("__", "")
    text = text.replace("`", "")

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    return text


def split_text(text):
    # Prefer natural sentence boundaries.
    sentences = re.split(
        r"(?<=[.!?])\s+",
        text
    )

    chunks = []
    current = ""

    for sentence in sentences:
        sentence = sentence.strip()

        if not sentence:
            continue

        if len(sentence) > MAX_CHARS:
            # Split unusually long sentences
            # at word boundaries only if necessary.
            words = sentence.split()
            pieces = []
            piece = ""

            for word in words:
                candidate = (
                    f"{piece} {word}".strip()
                )

                if len(candidate) > MAX_CHARS and piece:
                    pieces.append(piece)
                    piece = word
                else:
                    piece = candidate

            if piece:
                pieces.append(piece)

        else:
            pieces = [sentence]

        for piece in pieces:
            candidate = (
                f"{current} {piece}".strip()
            )

            if len(candidate) <= MAX_CHARS:
                current = candidate
            else:
                if current:
                    chunks.append(current)

                current = piece

    if current:
        chunks.append(current)

    return chunks


def trim_silence(audio, sample_rate):
    """
    Remove excessive model-generated silence
    at the beginning and end of each chunk.

    Preserve a small amount of padding so
    consonants do not get clipped.
    """

    audio = np.asarray(
        audio,
        dtype=np.float32
    ).reshape(-1)

    if audio.size == 0:
        raise RuntimeError("Empty audio chunk.")

    frame_size = max(
        1,
        round(sample_rate * 0.01)
    )

    frame_count = len(audio) // frame_size

    if frame_count == 0:
        return audio

    frames = audio[:frame_count * frame_size].reshape(
        frame_count,
        frame_size
    )

    rms = np.sqrt(
        np.mean(frames ** 2, axis=1)
    )

    peak = float(np.max(rms))

    threshold = max(
        0.001,
        peak * 0.02
    )

    active = np.where(rms > threshold)[0]

    if len(active) == 0:
        return audio

    padding = round(
        sample_rate * EDGE_PADDING_MS / 1000
    )

    start = max(
        0,
        int(active[0] * frame_size) - padding
    )

    end = min(
        len(audio),
        int((active[-1] + 1) * frame_size) + padding
    )

    return audio[start:end]


def smooth_edges(audio, sample_rate):
    """
    Apply very short fades to avoid clicking
    when independently generated chunks join.
    """

    audio = audio.copy()

    fade_samples = min(
        round(sample_rate * FADE_MS / 1000),
        len(audio) // 4
    )

    if fade_samples <= 0:
        return audio

    fade_in = np.linspace(
        0.0,
        1.0,
        fade_samples,
        dtype=np.float32
    )

    fade_out = np.linspace(
        1.0,
        0.0,
        fade_samples,
        dtype=np.float32
    )

    audio[:fade_samples] *= fade_in
    audio[-fade_samples:] *= fade_out

    return audio


def generate(test_mode=False):
    INPUT.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)

    for file in (MODEL, VOICES):
        if not file.is_file():
            raise FileNotFoundError(file)

    if test_mode:
        text = TEST_TEXT
        destination = TEST_AUDIO
    else:
        script = latest_script()

        print(f"Using script: {script.name}")

        text = clean_script(
            script.read_text(encoding="utf-8")
        )

        destination = NARRATION

    chunks = split_text(text)

    if not chunks:
        raise RuntimeError("No narration text found.")

    print("=" * 55)
    print("YOUTUBE AI - SMOOTH ADAM NARRATION")
    print("=" * 55)

    print(f"Voice: {VOICE}")
    print(f"Speed: {SPEED}")
    print(f"Chunks: {len(chunks)}")
    print(f"Pause: {PAUSE_SECONDS * 1000:.0f} ms")

    tts = Kokoro(
        str(MODEL),
        str(VOICES)
    )

    if VOICE not in tts.get_voices():
        raise RuntimeError(
            f"Voice unavailable: {VOICE}"
        )

    audio_parts = []
    sample_rate = None

    for index, chunk in enumerate(chunks, 1):
        print(
            f"Generating {index}/{len(chunks)}...",
            flush=True
        )

        audio, rate = tts.create(
            chunk,
            voice=VOICE,
            speed=SPEED,
            lang=LANGUAGE
        )

        if sample_rate is None:
            sample_rate = rate
        elif rate != sample_rate:
            raise RuntimeError(
                "Sample rate mismatch."
            )

        audio = trim_silence(
            audio,
            sample_rate
        )

        audio = smooth_edges(
            audio,
            sample_rate
        )

        audio_parts.append(audio)

        if index < len(chunks):
            pause = np.zeros(
                round(PAUSE_SECONDS * sample_rate),
                dtype=np.float32
            )

            audio_parts.append(pause)

    combined = np.concatenate(audio_parts)

    # Prevent clipping.
    peak = float(np.max(np.abs(combined)))

    if peak > 0.98:
        combined *= 0.98 / peak

    # Back up original narration if present.
    if not test_mode and NARRATION.exists():
        backup = INPUT / "narration_manual_backup.wav"

        if not backup.exists():
            shutil.copy2(NARRATION, backup)

    sf.write(
        str(destination),
        combined,
        sample_rate,
        subtype="PCM_16"
    )

    print("\nVOICE GENERATION COMPLETE")
    print(f"Saved: {destination}")
    print(f"Duration: {len(combined)/sample_rate:.2f}s")
    print(f"Sample rate: {sample_rate} Hz")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--test",
        action="store_true"
    )

    args = parser.parse_args()

    generate(test_mode=args.test)
