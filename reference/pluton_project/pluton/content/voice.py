"""
Free voice narration via edge-tts (Microsoft Edge's TTS, no API key needed).
Browse available voices from a terminal with: edge-tts --list-voices
"""

import asyncio
import edge_tts


async def _generate(text, voice, out_path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(out_path)


def synthesize(text, voice, out_path):
    """Generates an mp3 narration file. Blocking call."""
    asyncio.run(_generate(text, voice, out_path))
    return out_path
