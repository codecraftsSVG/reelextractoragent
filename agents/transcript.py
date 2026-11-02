"""TranscriptAgent: whisper transcription of spoken audio."""
from .tools import transcribe_audio

def transcribe(video_path: str, shortcode: str) -> dict:
    return transcribe_audio(video_path, shortcode)
