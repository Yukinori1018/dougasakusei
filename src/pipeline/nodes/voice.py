"""Voice node: TTS for AI segments + placeholder + manifest for user recordings."""
from __future__ import annotations

import wave
from pathlib import Path

import httpx

from ..schemas import AudioSegment, PipelineState, SegmentSpeaker
from ..settings import config, effective_mode, env
from ..utils.io import write_json, write_text
from ..utils.logging import get_logger

log = get_logger(__name__)


def _write_silent_wav(path: Path, seconds: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    framerate = 22050
    n = max(int(framerate * max(seconds, 0.5)), framerate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        w.writeframes(b"\x00\x00" * n)


def _elevenlabs_tts(text: str, out_path: Path) -> bool:
    api_key = env().ELEVENLABS_API_KEY
    voice_id = env().ELEVENLABS_VOICE_ID_AI
    if not api_key:
        return False
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {"xi-api-key": api_key, "accept": "audio/mpeg", "content-type": "application/json"}
    body = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.75},
    }
    try:
        with httpx.Client(timeout=120) as c:
            r = c.post(url, json=body, headers=headers)
            r.raise_for_status()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(r.content)
            return True
    except Exception as e:  # noqa: BLE001
        log.warning("ElevenLabs TTS failed: %s", e)
        return False


def _openai_tts(text: str, out_path: Path) -> bool:
    api_key = env().OPENAI_API_KEY
    if not api_key:
        return False
    url = "https://api.openai.com/v1/audio/speech"
    headers = {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}
    body = {"model": "tts-1-hd", "voice": "alloy", "input": text}
    try:
        with httpx.Client(timeout=120) as c:
            r = c.post(url, json=body, headers=headers)
            r.raise_for_status()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(r.content)
            return True
    except Exception as e:  # noqa: BLE001
        log.warning("OpenAI TTS failed: %s", e)
        return False


def _ai_tts(text: str, out_path: Path) -> bool:
    provider = config()["voice"]["ai_provider"]
    if provider == "elevenlabs" and _elevenlabs_tts(text, out_path):
        return True
    if _openai_tts(text, out_path):  # fallback
        return True
    return False


def run(state: PipelineState) -> PipelineState:
    log.info("[voice] generating audio segments")
    if state.script is None:
        return state

    pd = state.project_path()
    ai_dir = pd / "audio" / "ai_segments"
    user_dir = pd / "audio" / "user_segments"
    audio: list[AudioSegment] = []
    pending = []

    for seg in state.script.segments:
        if seg.speaker == SegmentSpeaker.AI:
            mp3 = ai_dir / f"seg_{seg.idx:03d}.mp3"
            ok = False
            if effective_mode() == "auto":
                ok = _ai_tts(seg.text, mp3)
            if not ok:
                wav = ai_dir / f"seg_{seg.idx:03d}.wav"
                _write_silent_wav(wav, seg.duration_est_sec or 5.0)
                audio.append(
                    AudioSegment(
                        segment_idx=seg.idx,
                        speaker=SegmentSpeaker.AI,
                        path=str(wav.relative_to(pd)),
                        duration_sec=seg.duration_est_sec,
                        placeholder=True,
                    )
                )
            else:
                audio.append(
                    AudioSegment(
                        segment_idx=seg.idx,
                        speaker=SegmentSpeaker.AI,
                        path=str(mp3.relative_to(pd)),
                        duration_sec=seg.duration_est_sec,
                    )
                )
        else:  # USER — leave a placeholder + record-this manifest entry
            placeholder = user_dir / f"seg_{seg.idx:03d}_RECORD_ME.wav"
            _write_silent_wav(placeholder, seg.duration_est_sec or 8.0)
            audio.append(
                AudioSegment(
                    segment_idx=seg.idx,
                    speaker=SegmentSpeaker.USER,
                    path=str(placeholder.relative_to(pd)),
                    duration_sec=seg.duration_est_sec,
                    placeholder=True,
                )
            )
            pending.append({"idx": seg.idx, "text": seg.text, "notes": seg.notes})

    state.audio = audio
    write_json(pd / "audio" / "manifest.json", audio)
    write_json(pd / "audio" / "user_segments" / "RECORD_ME.json", pending)
    write_text(
        pd / "audio" / "user_segments" / "README.md",
        "# 録音待ちセグメント\n\n"
        "`teleprompter.html` をブラウザで開き、各セグメントを録音してください。\n"
        "録音後、対応する `seg_NNN_RECORD_ME.wav` を `seg_NNN.wav` にリネームで完了です。\n"
        "対応一覧は `RECORD_ME.json` を参照。",
    )
    log.info("[voice] %d segments (pending user=%d)", len(audio), len(pending))
    return state
