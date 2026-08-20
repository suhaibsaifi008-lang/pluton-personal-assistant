"""
Builds burned-in captions. Timing is approximated by distributing the
script's words proportionally across the audio's actual duration (measured
via ffprobe) — simple, robust, and doesn't depend on any TTS library's
internal word-timing API.
"""

import json
import subprocess


def get_duration(audio_path):
    """Returns audio duration in seconds using ffprobe (part of ffmpeg)."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", audio_path],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def _format_timestamp(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(text, duration, out_path, words_per_caption=6):
    words = text.split()
    if not words:
        raise ValueError("No text to build captions from.")

    chunks = [words[i:i + words_per_caption] for i in range(0, len(words), words_per_caption)]
    total_words = len(words)

    t = 0.0
    lines = []
    for idx, chunk in enumerate(chunks, start=1):
        chunk_duration = duration * (len(chunk) / total_words)
        start, end = t, t + chunk_duration
        lines.append(str(idx))
        lines.append(f"{_format_timestamp(start)} --> {_format_timestamp(end)}")
        lines.append(" ".join(chunk))
        lines.append("")
        t = end

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return out_path
