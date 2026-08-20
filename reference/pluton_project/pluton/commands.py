"""All the things Pluton can actually do."""

import os
import subprocess
import webbrowser
import datetime
import ctypes

import psutil
import pywhatkit

import config
from pluton.files import FileManager, PermissionDenied
from pluton.writer import DocumentWriter
from pluton.vision import ScreenWatcher
from pluton.research import Researcher
from pluton.routines import RoutineRunner
from pluton.content.pipeline import ContentPipeline
from pluton.activity_log import get_logger
from pluton.safety import StopController
from pluton.planner import TaskPlanner
from pluton import permissions


class CommandRouter:
    """Matches spoken text to an action. Returns True if a command was handled."""

    def __init__(self, speaker, listener, brain=None):
        self.speaker = speaker
        self.listener = listener
        self.brain = brain
        self.logger = get_logger()

        self.files = FileManager()
        self.writer = DocumentWriter()
        self.vision = ScreenWatcher(speaker)
        self.researcher = Researcher()
        self.routines = RoutineRunner(self, speaker)
        self.content_pipeline = ContentPipeline(speaker)
        self.planner = TaskPlanner(self, speaker, self.logger)

        self.stop_controller = StopController()
        self.stop_controller.register("screen watch mode", self.vision.stop_watch)
        self.stop_controller.register("channel autopilot", self.content_pipeline.stop_autopilot)

    def handle(self, text: str) -> bool:
        if not text:
            return False

        self.logger.info(f"HEARD: {text}")

        # --- Emergency stop (kill switch) ---
        if any(p in text for p in ["emergency stop", "stop everything", "kill switch"]):
            stopped = self.stop_controller.stop_all()
            self.speaker.say(f"Stopped: {', '.join(stopped)}." if stopped else "Nothing was running.")
            self.logger.info(f"KILL SWITCH triggered. Stopped: {stopped}")
            return True

        # --- Multi-step task planning ---
        if text.startswith("task ") or text.startswith("do this task ") or text.startswith("handle this "):
            request = text.split(" ", 1)[1] if text.startswith("task ") else text
            for lead in ["do this task ", "handle this "]:
                request = request.replace(lead, "")
            self.planner.run(request.strip())
            return True

        # --- Permission gate ---
        level = permissions.classify(text)
        if level == 3:
            self.speaker.say("That's a restricted action. I don't perform those, by design.")
            self.logger.info(f"BLOCKED (level 3): {text}")
            return True
        if level == 2:
            if not permissions.confirm(self.speaker, self.listener, text):
                self.speaker.say("Cancelled.")
                self.logger.info(f"CANCELLED by user: {text}")
                return True
            self.logger.info(f"CONFIRMED (level 2): {text}")
            return False

        # --- Exit ---
        if any(w in text for w in ["exit", "quit", "shut down pluton", "stop listening"]):
            self.speaker.say("Going offline. Say the wake word anytime you need me.")
            raise SystemExit

        # --- Time / Date ---
        if "time" in text and "what" in text:
            now = datetime.datetime.now().strftime("%I:%M %p")
            self.speaker.say(f"It's {now}, {config.USER_NAME}.")
            return True

        if "date" in text and ("what" in text or "today" in text):
            today = datetime.datetime.now().strftime("%A, %B %d, %Y")
            self.speaker.say(f"Today is {today}.")
            return True

        # --- Open application ---
        if text.startswith("open ") or " open " in text:
            for key, path in config.APP_PATHS.items():
                if key in text:
                    return self._open_app(key, path)
            for key, url in config.WEBSITES.items():
                if key in text:
                    return self._open_website(key, url)

        # --- Web search (open browser tab) ---
        if "google" in text:
            query = text.replace("google", "").strip()
            if query:
                self.speaker.say(f"Searching for {query}")
                pywhatkit.search(query)
                return True

        # --- Web research (actually reads results and answers) ---
        if any(p in text for p in ["search for", "look up", "research", "find out about", "what does the internet say"]):
            query = text
            for p in ["search the web for", "search for", "look up", "research", "find out about", "what does the internet say about", "what does the internet say"]:
                query = query.replace(p, "")
            query = query.strip(" ,.-")
            if query:
                self.speaker.say(f"Looking that up.")
                answer = self.researcher.search(query)
                self.speaker.say(answer)
                return True

        # --- Routines / automations ---
        if "routine" in text:
            name = text
            for p in ["run my", "run the", "start my", "start the", "do my", "do the", "run", "start", "do", "routine"]:
                name = name.replace(p, "")
            name = name.strip(" ,.-")
            self.routines.run(name, config.ROUTINES)
            return True

        # --- YouTube ---
        if "play" in text and "youtube" not in text:
            song = text.replace("play", "").strip()
            if song:
                self.speaker.say(f"Playing {song} on YouTube")
                pywhatkit.playonyt(song)
                return True

        # --- Volume control ---
        if "volume up" in text:
            self._volume(True)
            self.speaker.say("Volume up.")
            return True
        if "volume down" in text:
            self._volume(False)
            self.speaker.say("Volume down.")
            return True
        if "mute" in text:
            self._mute()
            self.speaker.say("Muted.")
            return True

        # --- System stats ---
        if "battery" in text:
            batt = psutil.sensors_battery()
            if batt:
                self.speaker.say(f"Battery is at {int(batt.percent)} percent.")
            else:
                self.speaker.say("No battery detected — you're probably on a desktop.")
            return True

        if "cpu" in text or "how are you running" in text:
            usage = psutil.cpu_percent(interval=1)
            self.speaker.say(f"CPU usage is at {usage} percent.")
            return True

        # --- Power controls (confirm-based, safe defaults) ---
        if "shut down the computer" in text or "shutdown computer" in text:
            self.speaker.say("Shutting down in 10 seconds. Say cancel shutdown to stop.")
            os.system("shutdown /s /t 10")
            return True

        if "cancel shutdown" in text:
            os.system("shutdown /a")
            self.speaker.say("Shutdown cancelled.")
            return True

        if "lock" in text and "computer" in text:
            ctypes.windll.user32.LockWorkStation()
            self.speaker.say("Locking the computer.")
            return True

        # --- Screenshot ---
        if "screenshot" in text:
            self._screenshot()
            self.speaker.say("Screenshot saved.")
            return True

        # --- Screen vision ---
        if any(p in text for p in ["look at my screen", "what's on my screen", "what is on my screen", "help me with this", "guide me"]):
            self.speaker.say(self.vision.analyze_now())
            return True

        if "start watching" in text or ("watch mode" in text and "stop" not in text):
            started = self.vision.start_watch()
            if started:
                self.speaker.say(f"Watching your screen. I'll speak up if something needs attention. Check every {config.WATCH_INTERVAL} seconds.")
            elif not self.vision.enabled:
                self.speaker.say("I need an API key in config.py to watch your screen.")
            else:
                self.speaker.say("Already watching.")
            return True

        if "stop watching" in text:
            stopped = self.vision.stop_watch()
            self.speaker.say("Stopped watching your screen." if stopped else "I wasn't watching.")
            return True

        # --- Document creation (Word) ---
        if ("create" in text or "make" in text or "write" in text) and ("document" in text or "word doc" in text or "report" in text):
            brief = self._strip_lead(text, ["create", "make", "write", "a document about", "a word document about", "a report about", "document about", "document on", "about"])
            if not self.writer.enabled:
                self.speaker.say("I need an API key in config.py to write documents.")
                return True
            self.speaker.say(f"Writing the document on {brief}. This may take a minute for longer content.")
            try:
                path, count = self.writer.generate_docx(brief)
                self.speaker.say(f"Done. Created {count} sections and saved it to {path}")
            except Exception as e:
                self.speaker.say(f"I ran into an error writing that: {e}")
            return True

        # --- Spreadsheet creation (Excel) ---
        if ("create" in text or "make" in text) and ("spreadsheet" in text or "excel" in text):
            brief = self._strip_lead(text, ["create", "make", "an excel sheet about", "a spreadsheet about", "spreadsheet about", "excel about", "about"])
            if not self.writer.enabled:
                self.speaker.say("I need an API key in config.py to build spreadsheets.")
                return True
            self.speaker.say(f"Building the spreadsheet for {brief}.")
            try:
                path, count = self.writer.generate_xlsx(brief)
                self.speaker.say(f"Done. {count} rows saved to {path}")
            except Exception as e:
                self.speaker.say(f"I ran into an error building that: {e}")
            return True

        # --- Read an existing file ---
        if "read" in text and ("document" in text or "file" in text or ".docx" in text):
            name_hint = self._strip_lead(text, ["read", "the document", "the file", "document", "file", "called", "named"])
            matches = self.files.find_file(name_hint, extensions=("docx",))
            if not matches:
                self.speaker.say(f"I couldn't find a document matching {name_hint} in your allowed folders.")
                return True
            try:
                content = self.files.read_docx(matches[0])
                preview = content[:500]
                self.speaker.say(f"Here's the start of it: {preview}")
            except PermissionDenied as e:
                self.speaker.say(str(e))
            return True

        # --- YouTube content automation ---
        if ("start" in text) and ("channel" in text or "posting" in text or "content" in text) and "youtube" in text or "start autopilot" in text:
            started = self.content_pipeline.start_autopilot()
            if started:
                hrs = config.POSTING_INTERVAL_SECONDS / 3600
                self.speaker.say(f"Channel autopilot is on. Posting a new video roughly every {hrs:g} hours.")
            else:
                self.speaker.say("Autopilot is already running.")
            return True

        if ("stop" in text) and ("channel" in text or "posting" in text or "content" in text or "autopilot" in text):
            stopped = self.content_pipeline.stop_autopilot()
            self.speaker.say("Stopped the channel autopilot." if stopped else "It wasn't running.")
            return True

        if ("post a video" in text or "make a video" in text or "create a video" in text) and "now" in text:
            self.speaker.say("Generating a video now — this involves writing, voicing, and rendering, so it'll take a minute or two.")
            self.content_pipeline.run_once()
            return True

        # --- Fallback: send to AI brain for open-ended questions ---
        if self.brain and self.brain.enabled:
            answer = self.brain.ask(text)
            self.speaker.say(answer)
            return True

        self.speaker.say("I didn't catch a command for that. Add an API key in config.py so I can answer general questions too.")
        return False

    # ---------- helpers ----------

    def _strip_lead(self, text, phrases):
        """Removes leading command phrases so what's left is the actual subject,
        e.g. 'create a document about the Q3 budget' -> 'the Q3 budget'."""
        result = text
        for phrase in sorted(phrases, key=len, reverse=True):
            result = result.replace(phrase, "")
        return result.strip(" ,.-") or text

    def _open_app(self, name, path):
        expanded = os.path.expandvars(path)
        if os.path.exists(expanded):
            subprocess.Popen(expanded)
            self.speaker.say(f"Opening {name}")
        else:
            self.speaker.say(f"I couldn't find {name}. Check the path in config.py.")
        return True

    def _open_website(self, name, url):
        webbrowser.open(url)
        self.speaker.say(f"Opening {name}")
        return True

    def _volume(self, up: bool):
        # Uses virtual key codes: 0xAF = volume up, 0xAE = volume down
        key = 0xAF if up else 0xAE
        for _ in range(2):
            ctypes.windll.user32.keybd_event(key, 0, 0, 0)
            ctypes.windll.user32.keybd_event(key, 0, 2, 0)

    def _mute(self):
        ctypes.windll.user32.keybd_event(0xAD, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0xAD, 0, 2, 0)

    def _screenshot(self):
        import pyautogui  # imported lazily so it's only required if used
        pictures_dir = os.path.join(os.path.expanduser("~"), "Pictures")
        os.makedirs(pictures_dir, exist_ok=True)
        filename = f"pluton_screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        path = os.path.join(pictures_dir, filename)
        pyautogui.screenshot().save(path)
