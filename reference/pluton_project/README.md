# Pluton — Your PC Voice Assistant

A Windows voice assistant: say "Pluton" to wake it, then give it a command.
It can open apps/websites, search the web, play YouTube, control volume,
lock/shut down the PC, check battery/CPU, take screenshots, and answer
general questions via Claude.

## 1. Install Python

You need Python 3.10–3.12. Get it from https://python.org/downloads —
during install, **check "Add Python to PATH"**.

## 2. Install dependencies

Open Command Prompt in this folder and run:

```
pip install -r requirements.txt
pip install pyautogui
```

**If `pyaudio` fails to install** (common on Windows), run this instead:

```
pip install pipwin
pipwin install pyaudio
```

## 3. Set your microphone as default

Windows Settings → System → Sound → make sure your mic is the default input device.

## 4. (Optional but recommended) Add your Claude API key

Open `config.py` and paste your key into `ANTHROPIC_API_KEY`. Get one at
https://console.anthropic.com/settings/keys — this lets Pluton answer any
general question, not just fixed commands. Without it, Pluton still works
for all the built-in commands below, just not open-ended questions.

## 5. Set your app paths

Open `config.py` and edit `APP_PATHS` — replace the paths with wherever
your apps actually live on your PC (right-click a desktop shortcut →
Properties → Target, to find the exact path).

## 6. Run it

```
python main.py
```

Say **"Pluton"**, wait for it to say "Yes?", then say your command.

## Built-in commands

| Say something like...              | Pluton does                          |
|-------------------------------------|---------------------------------------|
| "Pluton, open chrome"               | Launches the app                      |
| "Pluton, open youtube"              | Opens the website                     |
| "Pluton, search for best keychains" | Google search in browser              |
| "Pluton, play [song name]"          | Plays it on YouTube                   |
| "Pluton, volume up / down / mute"   | Controls system volume                |
| "Pluton, what's the time"           | Tells current time                    |
| "Pluton, what's the date"           | Tells today's date                    |
| "Pluton, battery"                   | Battery percentage (laptops)          |
| "Pluton, cpu usage"                 | Current CPU load                      |
| "Pluton, take a screenshot"         | Saves to Pictures folder              |
| "Pluton, lock the computer"         | Locks Windows                         |
| "Pluton, shut down the computer"    | Shuts down in 10s (say "cancel shutdown" to stop) |
| "Pluton, create a document about [topic]" | Writes a full Word doc, section by section — no length cap |
| "Pluton, create a spreadsheet about [topic]" | Builds a real .xlsx with headers and rows |
| "Pluton, read the document called [name]" | Finds and reads back a file from your allowed folders |
| "Pluton, look at my screen" / "help me with this" | One-time screen analysis and guidance |
| "Pluton, start watching" | Turns on periodic screen monitoring (off by default) |
| "Pluton, stop watching" | Turns it back off |
| "Pluton, look up [question]" / "research [topic]" | Actually searches the web, reads results, and answers out loud |
| "Pluton, google [query]" | Opens a normal browser search tab (for when you want to read it yourself) |
| "Pluton, run my [name] routine" | Runs a custom automation — a sequence of commands defined in config.py |
| "Pluton, post a video now" | Generates and (if enabled) posts one YouTube Short right now |
| "Pluton, start my youtube channel" | Turns on autopilot — posts a new video on a timer, unattended |
| "Pluton, stop my youtube channel" | Turns autopilot off |
| "Pluton, task [complex multi-step request]" | Breaks the request into steps and executes them in order, with retries |
| "Pluton, emergency stop" | Immediately halts all background automation (watch mode, autopilot) |
| "Pluton, exit" / "quit"             | Stops Pluton                          |
| Anything else                       | Sent to Claude for an answer (if API key set) |

## File access, Word & Excel

Pluton can read, edit, and create Word and Excel files — but **only inside
folders you've explicitly allowed**. Edit `ALLOWED_FOLDERS` in `config.py`
to control exactly which folders it can touch (defaults to your Documents
and Desktop). Anything outside those folders is refused automatically.

New documents Pluton creates go to `DEFAULT_OUTPUT_FOLDER` (defaults to
`Documents\Pluton Files`) unless you specify otherwise.

**Document generation has no size cap** — for "create a document about X",
Pluton first asks Claude for an outline, then writes each section as a
separate API call and appends it to the file. A one-page brief and a
20-section report work the same way, it just takes longer for bigger ones.

For advanced use (editing a specific existing file, generating very
targeted content), you can also call the underlying modules directly from
Python — see `pluton/files.py` and `pluton/writer.py`.

## Screen monitoring ("guide me" mode)

Two modes, both opt-in:

- **On-demand** (default): say "Pluton, look at my screen" or "help me with
  this" any time — takes one screenshot, sends it to Claude, and Pluton
  tells you what it sees and how to proceed.
- **Watch mode** (off by default): say "Pluton, start watching" and it
  checks your screen every `WATCH_INTERVAL` seconds (default 30), and only
  speaks up if something looks worth flagging — an error, a stuck dialog,
  a likely mistake. Say "Pluton, stop watching" to turn it off.

**Important to know:** every screenshot in either mode is sent to the
Anthropic API to be analyzed. That means:
- Anything visible on screen (passwords, banking, private messages,
  personal documents) is included in that request — turn off watch mode
  before doing anything sensitive.
- Each check costs API usage. Watch mode running continuously will use
  noticeably more of your API quota than on-demand checks.
- There's no local-only vision mode currently — analysis requires the
  API key and an internet connection.

## Web research

"Pluton, look up [question]" or "research [topic]" actually searches the
web via Claude's search tool, reads the results, and speaks back a real
answer — not just a browser tab. "Pluton, google [query]" still opens a
normal browser search if you'd rather read it yourself.

## Routines (automations)

Define named routines in `config.py` under `ROUTINES` — each one is just a
list of ordinary Pluton commands, run in order:

```python
ROUTINES = {
    "study": ["open word", "open chrome", "volume down"],
    "morning": ["what's the time", "battery", "open gmail"],
}
```

Say "Pluton, run my study routine" and it executes each step exactly as if
you'd said them one at a time — a 1 second pause between steps so apps have
time to launch. Add as many routines and steps as you want; there's no
limit on either. This is the automation layer — chain together anything
Pluton can already do (open apps, control volume, read documents, run
research, even trigger another feature) into one voice command.

Note: routines run on a timer between steps, not on completion detection —
if a step needs an app to fully load before the next step makes sense
(e.g. logging into something), you may need to add extra steps or pauses
for slower apps.

## YouTube channel automation

Fully automated pipeline: Claude writes a Reddit-style story → free TTS
voices it → captions are generated and burned in → it's laid over
background footage you provide → it uploads to YouTube. No manual editing
step in between.

### One-time setup

**1. Install ffmpeg** (does the audio/video/caption assembly):
- Download from https://www.gyan.dev/ffmpeg/builds/ (get the "release essentials" build)
- Unzip it somewhere permanent, e.g. `C:\ffmpeg`
- Add `C:\ffmpeg\bin` to your Windows PATH (Settings → search "Environment
  Variables" → Path → New)
- Verify with `ffmpeg -version` in a new Command Prompt

**2. Add background footage**
Put a handful of `.mp4` loop/gameplay clips (Subway Surfers, Minecraft
parkour, satisfying loops — whatever fits your niche) into the folder set
by `BACKGROUND_VIDEOS_FOLDER` in `config.py`. Pluton picks one at random
per video and crops it to a vertical frame. This is the one piece there's
no free "generate from scratch" API for — the footage itself is templated,
everything else (script, voice, captions, editing, upload) is automated.

**3. Set up YouTube API access** (free, but you do this once yourself —
Pluton can't create Google credentials on your behalf):
- Go to https://console.cloud.google.com and create a project
- APIs & Services → Library → enable **"YouTube Data API v3"**
- APIs & Services → Credentials → Create Credentials → OAuth client ID →
  Application type: **Desktop app**
- Download the JSON, save it to the path set by `YOUTUBE_CLIENT_SECRETS`
  in `config.py`
- The first time Pluton uploads, a browser window opens asking you to log
  into the YouTube channel you want it posting to. After that it's cached
  in `YOUTUBE_TOKEN_FILE` and runs unattended.
- New Google Cloud projects start in "Testing" mode, which limits you to
  a small list of pre-approved Google accounts — add your own account
  under OAuth consent screen → Test users.

### Config you should look at before running

- `CONTENT_NICHE` — what kind of stories get written
- `YOUTUBE_PRIVACY` — starts as `"unlisted"` on purpose, so early videos
  don't go public before you've checked the quality. Switch to `"public"`
  once you're happy with it.
- `AUTO_POST_TO_YOUTUBE` — set to `False` to have it save videos locally
  instead of posting, if you want a review step after all.
- `POSTING_INTERVAL_SECONDS` — how often autopilot posts. Default is every
  6 hours.

### Running it

- "Pluton, post a video now" — runs the pipeline once, good for testing
- "Pluton, start my youtube channel" — turns on autopilot, posts on the
  timer above until you say "Pluton, stop my youtube channel"

### Worth knowing

- **YouTube API quota**: uploads cost 1600 quota units against a default
  daily budget of 10,000 — about 6 uploads/day on a fresh project before
  you'd need to request a quota increase from Google.
- **YouTube's policies on automated content**: YouTube has explicitly
  tightened rules around "mass-produced" and "repetitive" content —
  channels that are 100% templated with no meaningful variation or added
  value risk demonetization or removal under their spam/inauthentic
  content policy. Varying your story topics, titles, and background
  footage helps; a channel that's byte-for-byte the same format on every
  video is the pattern that gets flagged.
- **Cost**: each video costs a handful of Claude API calls (story + title)
  plus TTS is free. Not expensive, but not zero at scale.
- If a run fails partway (e.g. ffmpeg not on PATH, no background clips in
  the folder), Pluton will tell you what broke rather than posting a
  broken video.

## Task planning (Phase 1)

For requests too complex for a single command, say **"Pluton, task [request]"**
— e.g. "Pluton, task check my battery, take a screenshot, and tell me the time."
Claude breaks it into individual steps, each one runs through the normal
command system, failed steps retry once, and you get a summary at the end
(completed / failed counts). Every step is written to the activity log.

This only works for things Pluton can already do one command at a time —
it composes existing capabilities, it doesn't invent new ones. A step like
"click the blue button" won't work yet; there's no computer-control layer
for that (see "What's not built yet" below).

## Permission tiers & safety

Every command is classified before it runs:

- **Level 1 (safe)** — runs immediately: opening apps, reading, searching,
  screenshots, research, most of what Pluton does.
- **Level 2 (confirm first)** — shutdown, deleting, uploading, posting,
  sending, purchasing. Pluton asks out loud and waits for a clear "yes"
  before proceeding; anything else cancels it.
- **Level 3 (restricted)** — mass deletion, disabling security software,
  formatting drives, credential/private key access. These are hard-blocked
  in the code itself, not a config toggle — there's no setting that
  re-enables them, on purpose.

**Emergency stop**: say "Pluton, emergency stop" (or "stop everything")
any time to immediately halt screen watch mode and channel autopilot,
whatever's currently running.

**Activity log**: every command Pluton hears, every permission decision,
and every plan step is timestamped in `Logs/activity.log` inside your
Pluton Files folder (path set by `LOG_FOLDER` in config.py). This is your
audit trail — if you want to know what Pluton did while you were away,
this is where to look.

## What's not built yet

Being direct about the gap between this and the full Pluton spec, so nothing
here is overclaimed:

- **No mouse/keyboard computer-control layer** — Pluton can't click things
  or type into arbitrary windows yet. Screen vision is look-and-describe,
  not look-and-click.
- **No browser agent (Playwright)** — `webbrowser.open()` just launches a
  tab; nothing navigates pages, clicks elements, or reads content back.
- **No coding agent loop** — no run→observe→fix cycle; document/content
  generation is one-shot, not iteratively tested and debugged.
- **No true scheduler** — routines and tasks are voice-triggered, not
  time-triggered ("every morning at 8am" isn't wired up yet).
- **No desktop UI** — this is a terminal script; there's no chat window,
  task status view, or clickable permission approvals.

These map to Phases 2-8 of the original spec and are reasonable next steps,
each substantial enough to be its own build.

## Customizing

- **Change the wake word**: edit `WAKE_WORD` in `config.py`
- **Add more apps**: add a line to `APP_PATHS` in `config.py`
- **Add more websites**: add a line to `WEBSITES` in `config.py`
- **Add new voice commands**: open `pluton/commands.py` and add a new
  `if "your phrase" in text:` block inside `CommandRouter.handle()`

## Notes & limitations

- Speech recognition uses Google's free API, so **it needs internet** to
  understand your voice (TTS/speaking back works offline).
- It listens in short bursts, not truly "always on" — say the wake word,
  pause briefly, then speak your command.
- Windows only, due to the volume/lock/shutdown controls using Windows APIs.
- For hands-free background operation, right-click `main.py` → you can also
  create a `.bat` file with `python main.py` and put a shortcut to it in
  `shell:startup` to launch on boot.

## Troubleshooting

- **"Microphone not found"** — check Windows privacy settings allow apps
  to access your microphone (Settings → Privacy → Microphone).
- **It mishears the wake word** — try a more distinct wake word in
  `config.py`, e.g. `"hey pluton"`.
- **`pyaudio` install fails** — use the `pipwin` method in step 2 above.
