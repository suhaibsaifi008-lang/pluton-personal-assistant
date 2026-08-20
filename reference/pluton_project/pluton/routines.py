"""
Runs named "routines" — sequences of ordinary Pluton commands chained
together and triggered by one phrase. Define routines in config.py under
ROUTINES; each step is just plain text, exactly as you'd say it to Pluton.
"""

import time


class RoutineRunner:
    def __init__(self, router, speaker):
        self.router = router
        self.speaker = speaker

    def run(self, routine_name, routines_dict):
        steps = routines_dict.get(routine_name)
        if not steps:
            available = ", ".join(routines_dict.keys()) or "none set up yet"
            self.speaker.say(
                f"I don't have a routine called {routine_name}. "
                f"Available routines: {available}. Add new ones to ROUTINES in config.py."
            )
            return False

        self.speaker.say(f"Running {routine_name}. {len(steps)} steps.")
        for step in steps:
            try:
                self.router.handle(step.lower())
            except SystemExit:
                raise
            except Exception as e:
                print(f"Routine step failed ('{step}'): {e}")
            time.sleep(1)

        self.speaker.say(f"Done with {routine_name}.")
        return True
