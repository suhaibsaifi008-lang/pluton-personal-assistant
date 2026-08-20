"""Handles Pluton's spoken output."""

import pyttsx3
import config


class Speaker:
    def __init__(self):
        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", config.VOICE_RATE)

        voices = self.engine.getProperty("voices")
        if voices and config.VOICE_INDEX < len(voices):
            self.engine.setProperty("voice", voices[config.VOICE_INDEX].id)

    def say(self, text: str):
        print(f"Pluton: {text}")
        self.engine.say(text)
        self.engine.runAndWait()
