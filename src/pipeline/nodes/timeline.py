"""Timeline node: write OTIO + FCPXML + EDL for hand-off to NLE.

We intentionally do NOT invoke ffmpeg to render a final mp4 here — that step
depends on real media that the user supplies for placeholders. We emit a
preview-render script (`render_preview.sh`) that the user runs after recording
their voice segments.
"""
from __future__ import annotations

from pathlib import Path

import opentimelineio as otio

from ..schemas import PipelineState, TimelineOutputs
from ..utils.io import write_text
from ..utils.logging import get_logger

log = get_logger(__name__)


def _build_timeline(state: PipelineState) -> otio.schema.Timeline:
    timeline = otio.schema.Timeline(name=state.topic.title_working if state.topic else "video")
    video_track = otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video)
    audio_track = otio.schema.Track(name="A1", kind=otio.schema.TrackKind.Audio)
    timeline.tracks.append(video_track)
    timeline.tracks.append(audio_track)

    if state.script is None:
        return timeline

    fps = 30
    cursor = 0.0
    for seg in state.script.segments:
        dur = max(seg.duration_est_sec, 1.0)
        rng = otio.opentime.TimeRange(
            start_time=otio.opentime.RationalTime(0, fps),
            duration=otio.opentime.RationalTime(round(dur * fps), fps),
        )
        # Video — point at a placeholder visual; user fills in.
        ref_path = ""
        for v in state.visuals:
            if v.segment_idx == seg.idx and v.path:
                ref_path = v.path
                break
        media_ref = otio.schema.ExternalReference(target_url=ref_path or f"PLACEHOLDER_seg{seg.idx:03d}.mp4")
        video_clip = otio.schema.Clip(
            name=f"seg_{seg.idx:03d}_{seg.section}",
            media_reference=media_ref,
            source_range=rng,
        )
        video_track.append(video_clip)

        # Audio — match by segment_idx
        audio_path = next((a.path for a in state.audio if a.segment_idx == seg.idx), "")
        audio_ref = otio.schema.ExternalReference(target_url=audio_path or f"PLACEHOLDER_audio_{seg.idx:03d}.wav")
        audio_clip = otio.schema.Clip(
            name=f"audio_{seg.idx:03d}",
            media_reference=audio_ref,
            source_range=rng,
        )
        audio_track.append(audio_clip)
        cursor += dur

    return timeline


def _render_preview_script(state: PipelineState, output_mp4: Path) -> str:
    """Bash script that uses ffmpeg to assemble a preview from current audio + still frames."""
    pd = state.project_path()
    lines = ["#!/usr/bin/env bash", "set -euo pipefail", f"cd \"{pd}\"", ""]
    lines.append("# Generate a concat list from current audio segments.")
    lines.append("rm -f concat.txt")
    for a in sorted(state.audio, key=lambda x: x.segment_idx):
        lines.append(f"echo \"file '{a.path}'\" >> concat.txt")
    lines.append("ffmpeg -y -f concat -safe 0 -i concat.txt -c copy mixed.audio.wav || true")
    lines.append(
        "# Burn subtitles onto a black frame as a quick preview; real B-roll happens in NLE."
    )
    lines.append(
        "ffmpeg -y -f lavfi -i color=c=black:s=1920x1080:r=30 -i mixed.audio.wav "
        "-vf \"subtitles=subtitles/ja.srt\" -shortest -c:v libx264 -c:a aac "
        f"\"{output_mp4.name}\""
    )
    return "\n".join(lines) + "\n"


def run(state: PipelineState) -> PipelineState:
    log.info("[timeline] writing OTIO / FCPXML / EDL")
    pd = state.project_path()
    tl_dir = pd / "timeline"
    tl_dir.mkdir(parents=True, exist_ok=True)

    timeline = _build_timeline(state)
    out = TimelineOutputs()

    otio_path = tl_dir / "project.otio"
    otio.adapters.write_to_file(timeline, str(otio_path))
    out.otio_path = str(otio_path.relative_to(pd))

    try:
        fcp = tl_dir / "project.fcpxml"
        otio.adapters.write_to_file(timeline, str(fcp), adapter_name="fcpx_xml")
        out.fcpxml_path = str(fcp.relative_to(pd))
    except Exception as e:  # noqa: BLE001
        log.warning("FCPXML write skipped: %s", e)

    try:
        edl = tl_dir / "project.edl"
        otio.adapters.write_to_file(timeline, str(edl), adapter_name="cmx_3600")
        out.edl_path = str(edl.relative_to(pd))
    except Exception as e:  # noqa: BLE001
        log.warning("EDL write skipped: %s", e)

    preview_mp4 = pd / "output" / "preview.mp4"
    script_sh = pd / "render_preview.sh"
    write_text(script_sh, _render_preview_script(state, preview_mp4))
    script_sh.chmod(0o755)
    out.preview_mp4 = str(preview_mp4.relative_to(pd))

    state.timeline = out
    log.info("[timeline] OTIO=%s, FCPXML=%s", out.otio_path, out.fcpxml_path)
    return state
