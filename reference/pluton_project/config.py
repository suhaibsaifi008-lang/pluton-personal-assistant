"""
Pluton Configuration
Edit this file to customize your assistant.
"""

# Wake word — say this before every command, e.g. "Pluton, open chrome"
WAKE_WORD = "pluton"

# Name Pluton calls you
USER_NAME = "Suhaib"

# Voice settings (pyttsx3)
VOICE_RATE = 175          # words per minute
VOICE_INDEX = 0           # 0 = usually male voice, 1 = usually female (Windows SAPI5)

# Applications Pluton can open by voice.
# Add your own: "keyword you'll say": r"full path to the .exe"
APP_PATHS = {
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "notepad": r"C:\Windows\System32\notepad.exe",
    "calculator": r"C:\Windows\System32\calc.exe",
    "word": r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
    "excel": r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
    "vscode": r"C:\Users\%USERNAME%\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "spotify": r"C:\Users\%USERNAME%\AppData\Roaming\Spotify\Spotify.exe",
}

# Websites Pluton can open by voice.
# "keyword you'll say": "url"
WEBSITES = {
    "youtube": "https://youtube.com",
    "gmail": "https://mail.google.com",
    "instagram": "https://instagram.com",
    "chatgpt": "https://chat.openai.com",
    "claude": "https://claude.ai",
    "github": "https://github.com",
}

# Anthropic API key for the "brain" (general Q&A / chat).
# Get one at https://console.anthropic.com — leave blank to disable AI chat.
ANTHROPIC_API_KEY = ""

# Model used for general questions
CLAUDE_MODEL = "claude-sonnet-4-6"

# Speech recognition timeout settings (seconds)
LISTEN_TIMEOUT = 5
PHRASE_TIME_LIMIT = 8

# --- File access ---
# Pluton will ONLY read/write/create files inside these folders (and their
# subfolders). This is the "files I allow it to access" boundary — add or
# remove folders as you like. %USERNAME% is expanded automatically.
ALLOWED_FOLDERS = [
    r"C:\Users\%USERNAME%\Documents",
    r"C:\Users\%USERNAME%\Desktop",
    r"C:\Users\%USERNAME%\Documents\Pluton Files",
]

# Where brand-new documents Pluton creates get saved by default
DEFAULT_OUTPUT_FOLDER = r"C:\Users\%USERNAME%\Documents\Pluton Files"

# --- Screen vision ---
# How often (seconds) Pluton checks your screen when "watch mode" is on.
# Only used if you say "Pluton, start watching my screen".
WATCH_INTERVAL = 30

# --- Routines / automations ---
# Named sequences of commands, triggered by "Pluton, run my [name] routine".
# Each step is plain text, exactly as you'd say it to Pluton normally.
# Add as many routines as you want, and as many steps per routine.
ROUTINES = {
    "study": [
        "open word",
        "open chrome",
        "volume down",
    ],
    "morning": [
        "what's the time",
        "battery",
        "open gmail",
    ],
}

# --- YouTube content automation ---
# What kind of stories Pluton writes. Change freely.
CONTENT_NICHE = "Reddit-style story narration (AITA, relationship drama, revenge stories)"

# Finished videos and intermediate files land here
CONTENT_OUTPUT_FOLDER = r"C:\Users\%USERNAME%\Documents\Pluton Files\Content"

# Drop background/loop footage (gameplay, satisfying loops, etc.) here.
# Pluton picks one at random per video and crops it to fill a vertical frame.
BACKGROUND_VIDEOS_FOLDER = r"C:\Users\%USERNAME%\Documents\Pluton Files\Backgrounds"

# Free edge-tts voice. List more options in a terminal with: edge-tts --list-voices
TTS_VOICE = "en-US-GuyNeural"

CONTENT_TAGS = ["shorts", "story", "reddit"]

# One-time OAuth setup — see README "YouTube automation" section
YOUTUBE_CLIENT_SECRETS = r"C:\Users\%USERNAME%\Documents\Pluton Files\client_secret.json"
YOUTUBE_TOKEN_FILE = r"C:\Users\%USERNAME%\Documents\Pluton Files\youtube_token.pickle"

# Start on "unlisted" so you can check quality before anything goes public.
# Switch to "public" once you trust the output.
YOUTUBE_PRIVACY = "unlisted"

# True = autopilot posts straight to YouTube. False = saves videos locally
# for you to review and upload yourself.
AUTO_POST_TO_YOUTUBE = True

# How often autopilot generates + posts a new video, in seconds.
# 6 hours = 21600. Mind YouTube's daily upload quota on new/small channels.
POSTING_INTERVAL_SECONDS = 6 * 60 * 60

# --- Task planning & safety ---
# Where the activity log is written (every command Pluton hears + key actions)
LOG_FOLDER = r"C:\Users\%USERNAME%\Documents\Pluton Files\Logs"

# Max steps the task planner will break a complex request into
MAX_PLAN_STEPS = 8
