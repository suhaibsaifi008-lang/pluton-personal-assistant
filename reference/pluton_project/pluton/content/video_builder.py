"""
Assembles the final vertical video: loops/crops a background clip to fill
the frame, lays the narration audio over it, and burns in captions —
all in one ffmpeg pass. Requires ffmpeg installed and on PATH.
"""

import os
import glob
import random
import subprocess


def _find_background_clips(folder):
    clips = glob.glob(os.path.join(folder, "*.mp4"))
    if not clips:
        raise FileNotFoundError(
            f"No .mp4 files found in {folder}. Drop some background/loop "
            f"footage (gameplay, satisfying loops, etc.) in that folder first."
        )
    return clips


def build_video(background_folder, audio_path, srt_path, out_path, duration):
    bg_clip = random.choice(_find_background_clips(background_folder))

    # ffmpeg's subtitles filter needs colons escaped in Windows paths
    srt_for_filter = srt_path.replace("\\", "/").replace(":", "\\:")

    filter_complex = (
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        f"subtitles='{srt_for_filter}':force_style="
        "'FontName=Arial,FontSize=16,Bold=1,PrimaryColour=&HFFFFFF&,"
        "OutlineColour=&H000000&,BorderStyle=1,Outline=2,Alignment=2'[v]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", bg_clip,
        "-i", audio_path,
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "1:a",
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "veryfast",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        out_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-800:]}")
    return out_path
