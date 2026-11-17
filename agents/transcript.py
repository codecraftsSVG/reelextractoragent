"""TranscriptAgent: whisper transcription of spoken audio."""
import os

from .tools import transcribe_audio

def transcribe(video_path: str, shortcode: str) -> dict:
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    return transcribe_audio(video_path, shortcode)
