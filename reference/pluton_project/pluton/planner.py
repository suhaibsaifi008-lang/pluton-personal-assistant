"""
Task planner. Turns a complex request into an actual sequence:

    Understand -> Plan -> Act -> Observe -> Correct -> Complete

Instead of one LLM guess, Claude breaks the request into steps phrased as
plain Pluton commands, and each step runs through the normal command router
— so a step can be "open chrome", "look up the weather", "create a document
about X", anything Pluton already knows how to do. Failed steps retry a
limited number of times before being reported, not silently dropped.
"""

import config

try:
    import anthropic
except ImportError:
    anthropic = None


class TaskPlanner:
    def __init__(self, router, speaker, logger):
        self.router = router
        self.speaker = speaker
        self.logger = logger
        self.enabled = bool(config.ANTHROPIC_API_KEY) and anthropic is not None
        if self.enabled:
            self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def _plan(self, request):
        prompt = (
            "Break this request into a short list of simple steps. Each step "
            "must be phrasable as one short voice command a simple assistant "
            "could execute on its own, e.g. 'open chrome', 'take a screenshot', "
            "'what's the time', 'look up X', 'create a document about X', "
            "'read the document called X'. Don't invent steps the assistant "
            "couldn't plausibly do. Return ONLY the steps, one per line, no "
            f"numbering, no markdown, max {config.MAX_PLAN_STEPS} steps.\n\n"
            f"Request: {request}"
        )
        response = self.client.messages.create(
            model=config.CLAUDE_MODEL, max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        steps = [s.strip("-•* ").strip() for s in text.split("\n") if s.strip()]
        return steps[:config.MAX_PLAN_STEPS]

    def run(self, request, max_retries=1):
        if not self.enabled:
            self.speaker.say("I need an API key in config.py to plan multi-step tasks.")
            return

        self.logger.info(f"PLAN requested: {request}")
        steps = self._plan(request)
        if not steps:
            self.speaker.say("I couldn't break that into steps.")
            return

        self.speaker.say(f"Here's my plan — {len(steps)} steps. Starting now.")
        self.logger.info(f"PLAN steps: {steps}")

        completed, failed = 0, []
        for i, step in enumerate(steps, start=1):
            self.logger.info(f"STEP {i}/{len(steps)}: {step}")
            success = False

            for attempt in range(max_retries + 1):
                try:
                    self.router.handle(step.lower())
                    success = True
                    break
                except SystemExit:
                    raise
                except Exception as e:
                    self.logger.info(f"STEP {i} attempt {attempt + 1} failed: {e}")

            if success:
                completed += 1
                self.logger.info(f"STEP {i} completed")
            else:
                failed.append(step)
                self.logger.info(f"STEP {i} FAILED after retries")

        if failed:
            self.speaker.say(
                f"Done. {completed} of {len(steps)} steps completed, "
                f"{len(failed)} failed. Check the activity log for details."
            )
        else:
            self.speaker.say(f"Task complete. All {completed} steps finished.")
        self.logger.info(f"PLAN finished: {completed}/{len(steps)} completed, failed={failed}")
