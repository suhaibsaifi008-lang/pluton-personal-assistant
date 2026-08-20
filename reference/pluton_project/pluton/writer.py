"""
Generates full documents (Word or Excel) from a spoken brief.
Documents are built section-by-section, each with its own Claude call, so
there's no cap on total document length — a 3-page brief and a 50-page
report are handled the same way, just with more sections.
"""

import os
import re
import datetime

import config
from pluton.files import FileManager

try:
    import anthropic
except ImportError:
    anthropic = None


class DocumentWriter:
    def __init__(self):
        self.enabled = bool(config.ANTHROPIC_API_KEY) and anthropic is not None
        if self.enabled:
            self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.files = FileManager()

    def _slugify(self, text, max_len=40):
        slug = re.sub(r"[^\w\s-]", "", text).strip().replace(" ", "_")
        return slug[:max_len] or "document"

    def _ask(self, prompt, max_tokens=4096):
        response = self.client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()

    def generate_docx(self, brief, max_sections=15, path=None):
        """Outline first, then write each section separately and append.
        Returns (path, section_count)."""
        if not self.enabled:
            raise RuntimeError("No Anthropic API key set in config.py")

        outline = self._ask(
            f"Create a section outline for a Word document about: {brief}\n"
            f"Return ONLY the heading names, one per line, no numbering, "
            f"no markdown, max {max_sections} sections.",
            max_tokens=512,
        )
        headings = [h.strip("-•* ").strip() for h in outline.split("\n") if h.strip()]
        headings = headings[:max_sections] or ["Overview"]

        sections = []
        for heading in headings:
            body = self._ask(
                f"Write the '{heading}' section of a document about: {brief}\n"
                f"Write in full prose paragraphs. No markdown symbols, no headers "
                f"inside the text, just the paragraph content for this section.",
                max_tokens=4096,
            )
            sections.append((heading, body))

        if path is None:
            filename = f"{self._slugify(brief)}.docx"
            path = os.path.join(self.files.default_output, filename)

        self.files.create_docx(path, brief[:100], sections)
        return path, len(sections)

    def generate_xlsx(self, brief, path=None):
        """Asks Claude to produce structured tabular data as CSV-style text,
        then converts it into a real spreadsheet."""
        if not self.enabled:
            raise RuntimeError("No Anthropic API key set in config.py")

        raw = self._ask(
            f"Produce spreadsheet data for: {brief}\n"
            f"Return ONLY plain CSV — first line is the header row, each "
            f"following line is a data row, comma-separated. No markdown, "
            f"no code fences, no commentary. Include as many rows as are "
            f"genuinely useful.",
            max_tokens=4096,
        )

        lines = [ln for ln in raw.strip().split("\n") if ln.strip()]
        rows = [[cell.strip() for cell in ln.split(",")] for ln in lines]
        headers, data_rows = (rows[0], rows[1:]) if rows else ([], [])

        if path is None:
            filename = f"{self._slugify(brief)}.xlsx"
            path = os.path.join(self.files.default_output, filename)

        self.files.create_xlsx(path, headers, data_rows)
        return path, len(data_rows)

    def continue_docx(self, path, instruction):
        """Extends an EXISTING document with more content, e.g. 'add a
        conclusion section' or 'expand the third section'."""
        if not self.enabled:
            raise RuntimeError("No Anthropic API key set in config.py")

        existing = self.files.read_docx(path)
        addition = self._ask(
            f"Here is the current document:\n\n{existing[:6000]}\n\n"
            f"Instruction: {instruction}\n"
            f"Write ONLY the new content to add, in full prose paragraphs, "
            f"no markdown.",
            max_tokens=4096,
        )
        self.files.append_to_docx(path, addition)
        return path
