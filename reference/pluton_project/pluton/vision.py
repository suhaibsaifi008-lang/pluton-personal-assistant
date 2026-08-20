"""
Lets Pluton see your screen and help with whatever's on it.

Two modes:
- On-demand: "Pluton, look at my screen" — takes one screenshot, analyzes it, answers.
- Watch mode: "Pluton, start watching" — polls every WATCH_INTERVAL seconds and
  only speaks up if something looks like it needs attention. "Pluton, stop
  watching" turns it off. Off by default.

Every screenshot is sent to the Anthropic API for analysis — be mindful of
what's on screen (passwords, banking, private docs) when using this.
"""

import base64
import io
import time
import threading

from PIL import ImageGrab

import config

try:
    import anthropic
except ImportError:
    anthropic = None


class ScreenWatcher:
    def __init__(self, speaker):
        self.speaker = speaker
        self.enabled = bool(config.ANTHROPIC_API_KEY) and anthropic is not None
        if self.enabled:
            self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.watching = False
        self._thread = None

    def _capture_b64(self):
        img = ImageGrab.grab()
        img.thumbnail((1280, 1280))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=70)
        return base64.b64encode(buf.getvalue()).decode()

    def analyze_now(self, question=None):
        if not self.enabled:
            return "Screen vision isn't set up — add your API key in config.py."

        question = question or "What's on my screen, and how can you help with what I'm doing?"
        img_b64 = self._capture_b64()

        response = self.client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}},
                    {"type": "text", "text": question + " Keep it short and speakable — 2-4 sentences, no markdown."},
                ],
            }],
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()

    def start_watch(self):
        if self.watching or not self.enabled:
            return False
        self.watching = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        return True

    def stop_watch(self):
        was_watching = self.watching
        self.watching = False
        return was_watching

    def _watch_loop(self):
        while self.watching:
            try:
                summary = self.analyze_now(
                    "Look at my screen. Only respond if there's something genuinely "
                    "worth flagging — an error message, a stuck dialog, something that "
                    "looks like a mistake, or an obvious next step I might be missing. "
                    "If nothing stands out, reply with exactly one word: NOTHING."
                )
                if "NOTHING" not in summary.upper():
                    self.speaker.say(summary)
            except Exception as e:
                print(f"Watch mode error: {e}")

            for _ in range(config.WATCH_INTERVAL):
                if not self.watching:
                    break
                time.sleep(1)
