"""
Real web research — searches, reads the results, and gives you a spoken
answer, instead of just opening a browser tab and leaving you to read it.
Uses Claude's built-in web search tool via the API.
"""

import config

try:
    import anthropic
except ImportError:
    anthropic = None


class Researcher:
    def __init__(self):
        self.enabled = bool(config.ANTHROPIC_API_KEY) and anthropic is not None
        if self.enabled:
            self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def search(self, query):
        if not self.enabled:
            return "Web research isn't set up — add your API key in config.py."

        try:
            response = self.client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=600,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{
                    "role": "user",
                    "content": (
                        f"Search the web and answer this: {query}\n"
                        f"Give a short, speakable answer — 3-5 sentences, no markdown, "
                        f"no citation brackets, no source list, just the answer."
                    ),
                }],
            )
        except Exception as e:
            return f"I hit an error searching: {e}"

        text_blocks = [b.text for b in response.content if b.type == "text"]
        answer = " ".join(t.strip() for t in text_blocks if t.strip())
        return answer or "I searched but couldn't put together a clear answer."
