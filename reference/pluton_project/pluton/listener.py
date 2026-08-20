"""Handles microphone input and speech-to-text."""

import speech_recognition as sr
import config


class Listener:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 300
        self.recognizer.dynamic_energy_threshold = True
        self.mic = sr.Microphone()

        # Calibrate for ambient noise once at startup
        with self.mic as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=1)

    def listen_once(self, timeout=None, phrase_time_limit=None):
        """Listen for a single phrase and return lowercase text, or None."""
        timeout = timeout or config.LISTEN_TIMEOUT
        phrase_time_limit = phrase_time_limit or config.PHRASE_TIME_LIMIT

        with self.mic as source:
            try:
                audio = self.recognizer.listen(
                    source, timeout=timeout, phrase_time_limit=phrase_time_limit
                )
            except sr.WaitTimeoutError:
                return None

        try:
            text = self.recognizer.recognize_google(audio)
            print(f"You: {text}")
            return text.lower()
        except sr.UnknownValueError:
            return None
        except sr.RequestError:
            print("Speech recognition service unavailable (check internet).")
            return None

    def wait_for_wake_word(self):
        """Blocks until the wake word is heard. Returns True once detected."""
        while True:
            with self.mic as source:
                try:
                    audio = self.recognizer.listen(source, phrase_time_limit=3)
                except sr.WaitTimeoutError:
                    continue

            try:
                text = self.recognizer.recognize_google(audio).lower()
                if config.WAKE_WORD in text:
                    return True
            except (sr.UnknownValueError, sr.RequestError):
                continue
