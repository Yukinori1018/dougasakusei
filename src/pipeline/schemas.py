"""Pydantic schemas for every artifact that flows through the pipeline."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class Mode(str, Enum):
    AUTO = "auto"
    MOCK = "mock"


class Format(str, Enum):
    LONG = "long"
    SHORT = "short"


class Source(BaseModel):
    url: str
    title: str = ""
    domain: str = ""
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    snippet: str = ""
    is_primary: bool = False


class Topic(BaseModel):
    slug: str
    title_working: str
    hook: str
    target_audience: str
    keywords: list[str] = []
    rationale: str = ""
    competitors: list[str] = []
    sources: list[Source] = []


class Claim(BaseModel):
    """A single verifiable assertion in the script."""

    text: str
    source_urls: list[str] = []
    confidence: float = 1.0
    requires_disclaimer: bool = False


class SegmentSpeaker(str, Enum):
    USER = "user"        # human-recorded
    AI = "ai"            # TTS-generated


class ScriptSegment(BaseModel):
    idx: int
    speaker: SegmentSpeaker
    text: str
    section: str          # intro, body, conclusion, cta, etc.
    notes: str = ""       # delivery notes for user-recorded segments
    claims: list[Claim] = []
    visual_hint: str = ""  # what B-roll / chart should accompany
    duration_est_sec: float = 0.0


class Script(BaseModel):
    title: str
    summary: str
    segments: list[ScriptSegment]
    total_duration_est_sec: float = 0.0

    def user_segments(self) -> list[ScriptSegment]:
        return [s for s in self.segments if s.speaker == SegmentSpeaker.USER]

    def ai_segments(self) -> list[ScriptSegment]:
        return [s for s in self.segments if s.speaker == SegmentSpeaker.AI]


class FactCheckIssue(BaseModel):
    segment_idx: int
    claim: str
    severity: str         # low | medium | high
    reason: str
    suggested_fix: str = ""


class FactCheckReport(BaseModel):
    issues: list[FactCheckIssue] = []
    verified_claim_count: int = 0
    needs_human_review: bool = False
    primary_source_urls: list[str] = []


class AudioSegment(BaseModel):
    segment_idx: int
    speaker: SegmentSpeaker
    path: str             # relative path under project dir
    duration_sec: float = 0.0
    placeholder: bool = False  # True when user recording is still pending


class VisualAsset(BaseModel):
    kind: str             # broll | chart | thumbnail | screen_recording | placeholder
    path: str
    source: str = ""      # pexels | pixabay | flux | manim | local
    license: str = ""
    segment_idx: int | None = None
    query: str = ""
    accepted: bool = False  # True after human picks from candidates


class ThumbnailCandidate(BaseModel):
    variant: str          # A / B / C
    strategy: str         # e.g. "数字訴求", "驚き顔モチーフ", "Before/After"
    path: str
    title_overlay: str


class Metadata(BaseModel):
    title_candidates: list[str]
    chosen_title: str
    description: str
    tags: list[str]
    seo_competition_score: float = 0.0   # 0..1, 0 = wide open, 1 = saturated
    notes: str = ""


class ComplianceFinding(BaseModel):
    check: str            # hallucination | copyright | tax_law | inauthentic | ai_disclosure
    severity: str         # ok | info | warn | block
    detail: str
    suggestion: str = ""


class ComplianceReport(BaseModel):
    findings: list[ComplianceFinding] = []
    blocking: bool = False
    ai_disclosure_required: bool = True
    checklist_for_studio: list[str] = []


class ShortCandidate(BaseModel):
    idx: int
    start_sec: float
    end_sec: float
    hook: str
    rationale: str
    preview_gif: str = ""
    selected: bool = False


class TimelineOutputs(BaseModel):
    preview_mp4: str = ""
    otio_path: str = ""
    fcpxml_path: str = ""
    edl_path: str = ""


class ProjectConfig(BaseModel):
    slug: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    format: Format = Format.LONG
    topic: str
    seed_keywords: list[str] = []


class PipelineState(BaseModel):
    """The single state object passed through the LangGraph DAG."""

    config: ProjectConfig
    project_dir: str
    mode: Mode = Mode.AUTO

    topic: Topic | None = None
    sources: list[Source] = []
    script: Script | None = None
    factcheck: FactCheckReport | None = None
    audio: list[AudioSegment] = []
    visuals: list[VisualAsset] = []
    thumbnails: list[ThumbnailCandidate] = []
    subtitles_srt: str = ""
    bgm_path: str = ""
    metadata: Metadata | None = None
    compliance: ComplianceReport | None = None
    timeline: TimelineOutputs = TimelineOutputs()
    shorts: list[ShortCandidate] = []
    errors: list[str] = []

    def project_path(self) -> Path:
        return Path(self.project_dir)
