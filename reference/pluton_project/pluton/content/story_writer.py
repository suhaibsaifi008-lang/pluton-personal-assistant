"""Generates short, speakable Reddit-style story scripts and titles."""

import config

try:
    import anthropic
except ImportError:
    anthropic = None


class StoryWriter:
    def __init__(self):
        self.enabled = bool(config.ANTHROPIC_API_KEY) and anthropic is not None
        if self.enabled:
            self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def write_story(self, niche=None):
        niche = niche or config.CONTENT_NICHE
        response = self.client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=600,
            messages=[{
                "role": "user",
                "content": (
                    f"Write a short Reddit-style story narration script for a {niche} "
                    f"short-form video. 45-60 seconds read aloud (about 130-160 words). "
                    f"First-person, strong hook in the first sentence, clear ending. "
                    f"Return ONLY the spoken narration text — no title, no markdown, "
                    f"no stage directions."
                ),
            }],
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()

    def write_title(self, story_text):
        response = self.client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=60,
            messages=[{
                "role": "user",
                "content": (
                    f"Write one short, clickable YouTube Shorts title (under 90 characters) "
                    f"for this story:\n\n{story_text}\n\nReturn ONLY the title, no quotes."
                ),
            }],
        )
        return "".join(b.text for b in response.content if b.type == "text").strip().strip('"')
