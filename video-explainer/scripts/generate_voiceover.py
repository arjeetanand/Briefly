#!/usr/bin/env python3
"""Render explainer narration with the app's configured local Kokoro voice."""

from __future__ import annotations

import json
import math
import sys
import wave
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
VIDEO_ROOT = PROJECT_ROOT / "video-explainer"
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from config import load_environment, setting  # noqa: E402

load_environment()

if setting("TTS_PROVIDER").lower() != "kokoro":
    raise SystemExit("Set TTS_PROVIDER=kokoro in the project environment to match the live voice.")

from routes.pitch import _kokoro_audio  # noqa: E402


FPS = 30
BREATH_FRAMES = 24
OVERLAP_FRAMES = 18
scenes = json.loads((VIDEO_ROOT / "src" / "scenes.json").read_text())
voiceover_dir = VIDEO_ROOT / "public" / "voiceover"
voiceover_dir.mkdir(parents=True, exist_ok=True)


def timestamp(frame: int) -> str:
    milliseconds = round(frame * 1000 / FPS)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}"


timeline: dict[str, dict[str, int]] = {}
cues: list[str] = ["WEBVTT", ""]
start_frame = 0
for index, scene in enumerate(scenes):
    audio_path = voiceover_dir / f"{scene['id']}.wav"
    audio_path.write_bytes(_kokoro_audio(scene["voiceover"]))
    with wave.open(str(audio_path), "rb") as audio:
        if audio.getnchannels() != 1 or audio.getframerate() != 24_000 or audio.getsampwidth() != 2:
            raise RuntimeError(f"Unexpected audio format from Kokoro: {audio_path.name}")
        audio_frames = math.ceil(audio.getnframes() / audio.getframerate() * FPS)
    if audio_frames <= 0:
        raise RuntimeError(f"Kokoro generated an empty narration: {audio_path.name}")

    scene_frames = audio_frames + BREATH_FRAMES
    timeline[scene["id"]] = {"audioFrames": audio_frames, "durationInFrames": scene_frames}
    cues.extend(
        [
            f"{timestamp(start_frame)} --> {timestamp(start_frame + audio_frames)}",
            scene["subtitle"],
            "",
        ]
    )
    start_frame += scene_frames
    if index < len(scenes) - 1:
        start_frame -= OVERLAP_FRAMES

(voiceover_dir / "timings.json").write_text(json.dumps(timeline, indent=2) + "\n")
(voiceover_dir / "captions.vtt").write_text("\n".join(cues))
assert len(timeline) == 7 and start_frame > FPS * 30
print(f"Rendered {len(timeline)} Kokoro clips ({start_frame / FPS:.1f}s total).")
