"""
Emergency stop. Any long-running background process (screen watch mode,
channel autopilot, future scheduled jobs) registers a stop function here.
Saying "Pluton, emergency stop" calls all of them at once.
"""


class StopController:
    def __init__(self):
        self._targets = []

    def register(self, name, stop_fn):
        """stop_fn takes no args and returns True if it stopped something
        that was actually running, False/None otherwise."""
        self._targets.append((name, stop_fn))

    def stop_all(self):
        stopped = []
        for name, stop_fn in self._targets:
            try:
                if stop_fn():
                    stopped.append(name)
            except Exception as e:
                print(f"Error stopping {name}: {e}")
        return stopped
