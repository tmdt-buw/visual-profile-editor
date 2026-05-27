from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ArtifactPayload(BaseModel):
    name: str = 'artifact'
    media_type: str | None = None
    content: str
    content_encoding: Literal['text', 'base64'] = 'text'


class AnalysisRequest(BaseModel):
    text: str | None = None
    artifacts: list[ArtifactPayload] = Field(default_factory=list)


class ArtifactSummary(BaseModel):
    name: str
    kind: str
    evidence_count: int = 0
    notes: list[str] = Field(default_factory=list)


class SemanticCandidate(BaseModel):
    id: str
    label: str
    kind: str
    identifier: str | None = None
    source: str
    evidence: list[str] = Field(default_factory=list)
    confidence: float = 0.6


class ExtractedAttribute(BaseModel):
    id: str
    source: str
    path: str
    label: str
    value: str
    category: str
    value_type: str = 'string'
    confidence: float = 0.7


class MetadataCandidate(BaseModel):
    id: str
    property: str
    label: str
    category: str
    range: str = 'string'
    requirement_level: Literal['mandatory', 'recommended', 'optional'] = 'recommended'
    source: str
    evidence: list[str] = Field(default_factory=list)
    confidence: float = 0.6


class CandidateRequirement(BaseModel):
    id: str
    title: str
    description: str
    category: str
    source: str
    evidence: list[str] = Field(default_factory=list)
    confidence: float = 0.6


class CompetencyQuestion(BaseModel):
    id: str
    question: str
    category: str
    source: str
    evidence: str | None = None


class AnalysisResponse(BaseModel):
    artifacts: list[ArtifactSummary] = Field(default_factory=list)
    extracted_attributes: list[ExtractedAttribute] = Field(default_factory=list)
    requirements: list[CandidateRequirement] = Field(default_factory=list)
    semantic_candidates: list[SemanticCandidate] = Field(default_factory=list)
    metadata_candidates: list[MetadataCandidate] = Field(default_factory=list)
    competency_questions: list[CompetencyQuestion] = Field(default_factory=list)


class RecommendationRequest(BaseModel):
    analysis: AnalysisResponse | None = None
    requirements: list[CandidateRequirement] = Field(default_factory=list)
    semantic_candidates: list[SemanticCandidate] = Field(default_factory=list)
    metadata_candidates: list[MetadataCandidate] = Field(default_factory=list)


class ReuseRecommendation(BaseModel):
    id: str
    label: str
    vocabulary: str
    term_uri: str
    priority: int
    action: Literal['reuse', 'profile', 'extension'] = 'reuse'
    requirement_id: str | None = None
    candidate_id: str | None = None
    rationale: str
    confidence: float = 0.6


class RecommendationResponse(BaseModel):
    recommendations: list[ReuseRecommendation] = Field(default_factory=list)
    extension_candidates: list[MetadataCandidate] = Field(default_factory=list)


class ConstraintGenerationRequest(BaseModel):
    analysis: AnalysisResponse | None = None
    requirements: list[CandidateRequirement] = Field(default_factory=list)
    recommendations: list[ReuseRecommendation] = Field(default_factory=list)
    selected_recommendation_ids: list[str] = Field(default_factory=list)


class ConstraintGenerationResponse(BaseModel):
    shacl: str
    profile_draft: dict[str, Any]
    validation_notes: list[str] = Field(default_factory=list)
