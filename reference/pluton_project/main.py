"""
Pluton — Your PC Voice Assistant
Run this file to start Pluton. Say the wake word (default: "pluton"), then your command.
"""

import config
from pluton.speaker import Speaker
from pluton.listener import Listener
from pluton.brain import Brain
from pluton.commands import CommandRouter


def main():
    speaker = Speaker()
    listener = Listener()
    brain = Brain()
    router = CommandRouter(speaker, listener, brain)

    speaker.say(f"Pluton online. Say '{config.WAKE_WORD}' to give me a command, {config.USER_NAME}.")

    while True:
        try:
            print(f"\nListening for wake word '{config.WAKE_WORD}'...")
            listener.wait_for_wake_word()

            speaker.say("Yes?")
            text = listener.listen_once()

            if text is None:
                speaker.say("I didn't catch that.")
                continue

            router.handle(text)

        except SystemExit:
            break
        except KeyboardInterrupt:
            speaker.say("Shutting down. Goodbye.")
            break
        except Exception as e:
            print(f"Error: {e}")
            speaker.say("Something went wrong, but I'm still running.")


if __name__ == "__main__":
    main()
