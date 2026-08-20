"""General-purpose Q&A brain, powered by Claude, for anything that isn't a system command."""

import config

try:
    import anthropic
except ImportError:
    anthropic = None


class Brain:
    def __init__(self):
        self.enabled = bool(config.ANTHROPIC_API_KEY) and anthropic is not None
        if self.enabled:
            self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.history = []

    def ask(self, question: str) -> str:
        if not self.enabled:
            return "AI chat isn't set up. Add your Anthropic API key in config.py."

        self.history.append({"role": "user", "content": question})
        # Keep the last 10 turns so it doesn't grow unbounded
        self.history = self.history[-10:]

        try:
            response = self.client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=300,
                system=(
                    "You are Pluton, a concise voice assistant running on the user's PC. "
                    "Keep answers short and speakable — 1-3 sentences unless asked for detail. "
                    "No markdown, no lists, no headers, since this is read aloud."
                ),
                messages=self.history,
            )
            answer = "".join(
                block.text for block in response.content if block.type == "text"
            )
            self.history.append({"role": "assistant", "content": answer})
            return answer.strip()
        except Exception as e:
            return f"I hit an error reaching Claude: {e}"
