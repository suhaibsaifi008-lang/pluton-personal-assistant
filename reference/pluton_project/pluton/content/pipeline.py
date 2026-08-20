"""
End-to-end pipeline: story -> voice -> captions -> video -> upload.
Also runs as a background autopilot that posts on a timer.
"""

import os
import time
import threading
import datetime

import config
from pluton.content.story_writer import StoryWriter
from pluton.content.voice import synthesize
from pluton.content.captions import get_duration, build_srt
from pluton.content.video_builder import build_video
from pluton.content.youtube_upload import YouTubeUploader


class ContentPipeline:
    def __init__(self, speaker):
        self.speaker = speaker
        self.story_writer = StoryWriter()
        self.uploader = YouTubeUploader()
        self.running = False
        self._thread = None
        self.output_folder = os.path.expandvars(config.CONTENT_OUTPUT_FOLDER)
        os.makedirs(self.output_folder, exist_ok=True)

    def run_once(self):
        """Generates and (if enabled) posts one video. Returns the video id
        (if posted), local path (if not), or None on failure."""
        if not self.story_writer.enabled:
            self.speaker.say("I need an API key in config.py to write stories.")
            return None

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        base = os.path.join(self.output_folder, ts)
        audio_path, srt_path, video_path = base + ".mp3", base + ".srt", base + ".mp4"

        try:
            story = self.story_writer.write_story()
            title = self.story_writer.write_title(story)

            synthesize(story, config.TTS_VOICE, audio_path)
            duration = get_duration(audio_path)
            build_srt(story, duration, srt_path)
            build_video(
                os.path.expandvars(config.BACKGROUND_VIDEOS_FOLDER),
                audio_path, srt_path, video_path, duration,
            )
        except Exception as e:
            self.speaker.say(f"Video generation failed: {e}")
            return None

        if not config.AUTO_POST_TO_YOUTUBE:
            self.speaker.say(f"Video ready at {video_path}. Auto-post is off in config.py.")
            return video_path

        try:
            description = story[:400] + "\n\n#shorts #storytime"
            video_id = self.uploader.upload(
                video_path, title, description,
                tags=config.CONTENT_TAGS, privacy=config.YOUTUBE_PRIVACY,
            )
            self.speaker.say(f"Posted to YouTube: {title}")
            return video_id
        except Exception as e:
            self.speaker.say(f"Video is ready but the upload failed: {e}")
            return video_path

    def start_autopilot(self):
        if self.running:
            return False
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def stop_autopilot(self):
        was_running = self.running
        self.running = False
        return was_running

    def _loop(self):
        while self.running:
            try:
                self.run_once()
            except Exception as e:
                print(f"Pipeline error: {e}")

            for _ in range(config.POSTING_INTERVAL_SECONDS):
                if not self.running:
                    break
                time.sleep(1)
