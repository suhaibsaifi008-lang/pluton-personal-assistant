"""
Permission tiers, per the security model in the spec:

Level 1 — Safe: runs immediately (reading, searching, screenshots, opening apps).
Level 2 — Requires confirmation: Pluton asks out loud before proceeding
  (shutdown, deleting, uploading/posting, sending, purchasing).
Level 3 — Restricted: hard-blocked, always. Not configurable, on purpose —
  this project will never wire up actions like disabling security software,
  mass deletion, or credential access as things a voice command can trigger.
  That boundary isn't meant to be reopened from config.py.
"""

LEVEL_2_KEYWORDS = [
    "shut down the computer", "shutdown computer",
    "post a video", "post to youtube",
    "start my pluton channel", "start my youtube channel",
    "delete", "send", "upload", "purchase", "buy",
]

LEVEL_3_KEYWORDS = [
    "delete all", "delete everything", "format the drive", "format drive",
    "disable antivirus", "disable firewall", "disable security",
    "wipe the drive", "credentials", "password file", "private key",
    "disable windows defender",
]


def classify(text: str) -> int:
    lowered = text.lower()
    if any(k in lowered for k in LEVEL_3_KEYWORDS):
        return 3
    if any(k in lowered for k in LEVEL_2_KEYWORDS):
        return 2
    return 1


def confirm(speaker, listener, action_description: str) -> bool:
    """Voice confirmation gate for Level 2 actions. Returns True only on a
    clear yes within the listen window; anything else cancels the action."""
    speaker.say(f"That needs confirmation: {action_description}. Say yes to proceed, or no to cancel.")
    response = listener.listen_once(timeout=8, phrase_time_limit=4)
    if not response:
        return False
    return any(w in response for w in ["yes", "confirm", "go ahead", "proceed", "do it"])
