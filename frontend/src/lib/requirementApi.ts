import type { SchemaModel } from '../types';

export type ArtifactPayload = {
  name: string;
  media_type?: string;
  content: string;
  content_encoding?: 'text' | 'base64';
};

export type AnalysisRequest = {
  text?: string;
  artifacts: ArtifactPayload[];
};

export type ArtifactSummary = {
  name: string;
  kind: string;
  evidence_count: number;
  notes: string[];
};

export type CandidateRequirement = {
  id: string;
  title: string;
  description: string;
  category: string;
  source: string;
  evidence: string[];
  confidence: number;
};

export type SemanticCandidate = {
  id: string;
  label: string;
  kind: string;
  identifier?: string | null;
  source: string;
  evidence: string[];
  confidence: number;
};

export type ExtractedAttribute = {
  id: string;
  source: string;
  path: string;
  label: string;
  value: string;
  category: string;
  value_type: string;
  confidence: number;
};

export type MetadataCandidate = {
  id: string;
  property: string;
  label: string;
  category: string;
  range: string;
  requirement_level: 'mandatory' | 'recommended' | 'optional';
  source: string;
  evidence: string[];
  confidence: number;
};

export type CompetencyQuestion = {
  id: string;
  question: string;
  category: string;
  source: string;
  evidence?: string | null;
};

export type AnalysisResponse = {
  artifacts: ArtifactSummary[];
  extracted_attributes: ExtractedAttribute[];
  requirements: CandidateRequirement[];
  semantic_candidates: SemanticCandidate[];
  metadata_candidates: MetadataCandidate[];
  competency_questions: CompetencyQuestion[];
};

export type ReuseRecommendation = {
  id: string;
  label: string;
  vocabulary: string;
  term_uri: string;
  priority: number;
  action: 'reuse' | 'profile' | 'extension';
  requirement_id?: string | null;
  candidate_id?: string | null;
  rationale: string;
  confidence: number;
};

export type RecommendationResponse = {
  recommendations: ReuseRecommendation[];
  extension_candidates: MetadataCandidate[];
};

export type ConstraintGenerationResponse = {
  shacl: string;
  profile_draft: SchemaModel;
  validation_notes: string[];
};

async function postJson<T>(endpoint: string, payload: unknown): Promise<T> {
  const response = await fetch(`/api/requirements/${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await response.text());
  return (await response.json()) as T;
}

export function analyzeArtifacts(payload: AnalysisRequest) {
  return postJson<AnalysisResponse>('analyze-artifacts', payload);
}

export function extractRequirements(payload: AnalysisRequest) {
  return postJson<AnalysisResponse>('extract-requirements', payload);
}

export function recommendReuse(analysis: AnalysisResponse) {
  return postJson<RecommendationResponse>('recommend-reuse', { analysis });
}

export function generateShacl(analysis: AnalysisResponse, recommendations: ReuseRecommendation[], selectedRecommendationIds: string[]) {
  return postJson<ConstraintGenerationResponse>('generate-shacl', {
    analysis,
    recommendations,
    selected_recommendation_ids: selectedRecommendationIds,
  });
}
