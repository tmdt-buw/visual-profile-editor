import { useCallback, useEffect, useMemo, useState, type DragEvent } from 'react';
import { CheckSquare, FileCode, FileSearch, GitMerge, RefreshCw, Search, Wand2 } from 'lucide-react';
import {
  analyzeArtifacts,
  extractRequirements,
  generateShacl,
  recommendReuse,
  type AnalysisRequest,
  type AnalysisResponse,
  type ArtifactPayload,
  type CandidateRequirement,
  type ExtractedAttribute,
  type ReuseRecommendation,
} from '../lib/requirementApi';
import { downloadText } from '../lib/schemaApi';
import { useEditorStore } from '../store';
import type { SchemaModel } from '../types';

type RequirementWorkbenchProps = {
  initialView: 'requirements' | 'reuse';
  onStatus: (status: string) => void;
};

type WorkbenchView = 'requirements' | 'reuse' | 'constraints';

const SAMPLE_TEXT =
  'Datasets should provide title, description, lifecycle phase, license, format, schema version, semantic anchors to AAS submodels or IFC entities, and asset type keywords for discovery.';

const ARTIFACT_ACCEPT = '.txt,.md,.json,.aasx,.jsonld,.ttl,.rdf,.owl,.ifc,.ifcspf';

export function RequirementWorkbench({ initialView, onStatus }: RequirementWorkbenchProps) {
  const mergeSchema = useEditorStore((state) => state.mergeSchema);
  const [view, setView] = useState<WorkbenchView>(initialView);
  const [text, setText] = useState(SAMPLE_TEXT);
  const [artifacts, setArtifacts] = useState<ArtifactPayload[]>([]);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [recommendations, setRecommendations] = useState<ReuseRecommendation[]>([]);
  const [accepted, setAccepted] = useState<Record<string, boolean>>({});
  const [shacl, setShacl] = useState('');
  const [profileDraft, setProfileDraft] = useState<AnalysisResponse | null>(null);
  const [generatedProfile, setGeneratedProfile] = useState<SchemaModel | null>(null);
  const [draggingArtifacts, setDraggingArtifacts] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setView(initialView);
  }, [initialView]);

  const requestPayload = useMemo<AnalysisRequest>(() => ({ text, artifacts }), [artifacts, text]);

  const acceptedRecommendationIds = useMemo(
    () => recommendations.filter((recommendation) => accepted[recommendation.id] !== false).map((recommendation) => recommendation.id),
    [accepted, recommendations],
  );

  const runAnalyze = useCallback(async () => {
    setBusy(true);
    onStatus('Analyzing artifacts...');
    try {
      const result = await analyzeArtifacts(requestPayload);
      setAnalysis(result);
      setShacl('');
      setGeneratedProfile(null);
      onStatus(`Analyzed ${result.artifacts.length} artifact(s), found ${result.requirements.length} requirement candidate(s).`);
      return result;
    } catch (error) {
      onStatus(`Requirement analysis failed: ${error instanceof Error ? error.message : 'unknown error'}`);
      throw error;
    } finally {
      setBusy(false);
    }
  }, [onStatus, requestPayload]);

  const runExtract = useCallback(async () => {
    setBusy(true);
    setView('requirements');
    onStatus('Extracting requirement candidates...');
    try {
      const result = await extractRequirements(requestPayload);
      setAnalysis(result);
      setShacl('');
      setGeneratedProfile(null);
      onStatus(`Extracted ${result.requirements.length} requirement candidate(s).`);
      return result;
    } catch (error) {
      onStatus(`Requirement extraction failed: ${error instanceof Error ? error.message : 'unknown error'}`);
      throw error;
    } finally {
      setBusy(false);
    }
  }, [onStatus, requestPayload]);

  const runRecommend = useCallback(async () => {
    setBusy(true);
    setView('reuse');
    onStatus('Recommending reusable vocabulary terms...');
    try {
      const currentAnalysis = analysis ?? (await analyzeArtifacts(requestPayload));
      setAnalysis(currentAnalysis);
      const result = await recommendReuse(currentAnalysis);
      setRecommendations(result.recommendations);
      setAccepted(Object.fromEntries(result.recommendations.map((recommendation) => [recommendation.id, true])));
      onStatus(`Prepared ${result.recommendations.length} reuse recommendation(s).`);
      return result.recommendations;
    } catch (error) {
      onStatus(`Reuse recommendation failed: ${error instanceof Error ? error.message : 'unknown error'}`);
      throw error;
    } finally {
      setBusy(false);
    }
  }, [analysis, onStatus, requestPayload]);

  const runGenerate = useCallback(async () => {
    setBusy(true);
    setView('constraints');
    onStatus('Generating SHACL and profile draft...');
    try {
      const currentAnalysis = analysis ?? (await analyzeArtifacts(requestPayload));
      setAnalysis(currentAnalysis);
      const currentRecommendations = recommendations.length ? recommendations : (await recommendReuse(currentAnalysis)).recommendations;
      if (!recommendations.length) {
        setRecommendations(currentRecommendations);
        setAccepted(Object.fromEntries(currentRecommendations.map((recommendation) => [recommendation.id, true])));
      }
      const result = await generateShacl(currentAnalysis, currentRecommendations, acceptedRecommendationIds);
      setShacl(result.shacl);
      setGeneratedProfile(result.profile_draft);
      setProfileDraft(currentAnalysis);
      onStatus('Generated SHACL and editable profile draft.');
    } catch (error) {
      onStatus(`Constraint generation failed: ${error instanceof Error ? error.message : 'unknown error'}`);
      throw error;
    } finally {
      setBusy(false);
    }
  }, [acceptedRecommendationIds, analysis, onStatus, recommendations, requestPayload]);

  const importFiles = useCallback(async (files: FileList | File[] | null) => {
    if (!files?.length) return;
    const loaded = await Promise.all(Array.from(files).map(fileToArtifact));
    setArtifacts((current) => [...current, ...loaded]);
    onStatus(`Loaded ${loaded.length} artifact file(s) for requirement extraction.`);
  }, [onStatus]);

  const onDropArtifacts = useCallback(
    async (event: DragEvent<HTMLElement>) => {
      event.preventDefault();
      event.stopPropagation();
      setDraggingArtifacts(false);
      await importFiles(event.dataTransfer.files);
    },
    [importFiles],
  );

  function mergeDraft() {
    if (!generatedProfile) return;
    mergeSchema(generatedProfile);
    onStatus('Merged generated requirement profile draft into the visual editor. Review before saving.');
  }

  return (
    <main className="requirement-workbench">
      <section
        className={`requirement-input-panel ${draggingArtifacts ? 'requirement-input-panel--dragging' : ''}`}
        onDragEnter={(event) => {
          event.preventDefault();
          event.stopPropagation();
          setDraggingArtifacts(true);
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          event.stopPropagation();
          if (event.currentTarget === event.target) setDraggingArtifacts(false);
        }}
        onDragOver={(event) => {
          event.preventDefault();
          event.dataTransfer.dropEffect = 'copy';
        }}
        onDrop={(event) => void onDropArtifacts(event)}
      >
        <div className="requirement-input-panel__header">
          <div>
            <h2>Requirement Extraction</h2>
            <p>Analyze heterogeneous construction artifacts for discovery-level profile requirements.</p>
          </div>
          <label className="file-picker">
            <FileSearch size={16} />
            Add files
            <input accept={ARTIFACT_ACCEPT} multiple onChange={(event) => void importFiles(event.target.files)} type="file" />
          </label>
        </div>

        <div className="artifact-drop-zone">
          <FileSearch size={18} />
          <span>Drop artifacts</span>
          <small>Text, AAS JSON, AASX, DCAT/RDF, IFC</small>
        </div>

        <textarea aria-label="Requirement text" className="requirement-textarea" onChange={(event) => setText(event.target.value)} value={text} />

        {artifacts.length ? (
          <div className="artifact-list">
            {artifacts.map((artifact) => (
              <span key={`${artifact.name}-${artifact.content.length}`}>{artifact.name}</span>
            ))}
          </div>
        ) : null}

        <div className="requirement-actions">
          <button disabled={busy} onClick={() => void runAnalyze()} type="button">
            <Search size={16} />
            Analyze
          </button>
          <button disabled={busy} onClick={() => void runExtract()} type="button">
            <CheckSquare size={16} />
            Extract
          </button>
          <button disabled={busy} onClick={() => void runRecommend()} type="button">
            <RefreshCw size={16} />
            Recommend
          </button>
          <button className="primary" disabled={busy} onClick={() => void runGenerate()} type="button">
            <Wand2 size={16} />
            Generate
          </button>
        </div>
      </section>

      <section className="requirement-review-panel">
        <div className="workflow-tabs">
          {[
            ['requirements', 'Requirements'],
            ['reuse', 'Reuse'],
            ['constraints', 'SHACL Draft'],
          ].map(([id, label]) => (
            <button className={view === id ? 'active' : undefined} key={id} onClick={() => setView(id as WorkbenchView)} type="button">
              {label}
            </button>
          ))}
        </div>

        {view === 'requirements' ? (
          <RequirementResults analysis={analysis} />
        ) : view === 'reuse' ? (
          <ReuseResults accepted={accepted} recommendations={recommendations} setAccepted={setAccepted} />
        ) : (
          <section className="constraint-preview">
            <div className="constraint-preview__actions">
              <button disabled={!shacl} onClick={() => downloadText(shacl, 'requirement-profile.shacl.ttl', 'text/turtle')} type="button">
                <FileCode size={16} />
                SHACL
              </button>
              <button disabled={!generatedProfile} onClick={mergeDraft} type="button">
                <GitMerge size={16} />
                Merge Draft
              </button>
            </div>
            {profileDraft ? <p className="muted">Draft generated from {profileDraft.requirements.length} reviewed requirement candidate(s).</p> : null}
            <pre>{shacl || 'Generate SHACL to preview profile constraints.'}</pre>
          </section>
        )}
      </section>
    </main>
  );
}

async function fileToArtifact(file: File): Promise<ArtifactPayload> {
  if (/\.aasx$/i.test(file.name)) {
    return {
      name: file.name,
      media_type: file.type || 'application/asset-administration-shell-package',
      content: arrayBufferToBase64(await file.arrayBuffer()),
      content_encoding: 'base64',
    };
  }

  return {
    name: file.name,
    media_type: file.type || undefined,
    content: await file.text(),
    content_encoding: 'text',
  };
}

function arrayBufferToBase64(buffer: ArrayBuffer) {
  const bytes = new Uint8Array(buffer);
  const chunkSize = 0x8000;
  let binary = '';
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return window.btoa(binary);
}

function RequirementResults({ analysis }: { analysis: AnalysisResponse | null }) {
  if (!analysis) {
    return <EmptyState text="Analyze text, AAS JSON, DCAT metadata, or lightweight IFC snippets to see candidate requirements." />;
  }

  const grouped = groupByCategory(analysis.requirements);

  return (
    <div className="result-grid">
      <SummaryStrip analysis={analysis} />
      <ExtractedAttributes attributes={analysis.extracted_attributes} />
      {Object.entries(grouped).map(([category, requirements]) => (
        <section className="result-section" key={category}>
          <h3>{category}</h3>
          <div className="candidate-list">
            {requirements.map((requirement) => (
              <article className="candidate-item" key={requirement.id}>
                <strong>{requirement.title}</strong>
                <p>{requirement.description}</p>
                <small>{formatConfidence(requirement.confidence)} confidence - {requirement.source}</small>
              </article>
            ))}
          </div>
        </section>
      ))}
      <section className="result-section">
        <h3>Competency Questions</h3>
        <div className="candidate-list">
          {analysis.competency_questions.map((question) => (
            <article className="candidate-item" key={question.id}>
              <strong>{question.question}</strong>
              <small>{question.category}</small>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

function ExtractedAttributes({ attributes }: { attributes: ExtractedAttribute[] }) {
  if (!attributes.length) return null;

  return (
    <section className="result-section">
      <h3>Extracted Attributes</h3>
      <div className="attribute-table" role="table" aria-label="Extracted artifact attributes">
        <div className="attribute-table__header" role="row">
          <span>Attribute</span>
          <span>Value</span>
          <span>Path</span>
          <span>Source</span>
        </div>
        {attributes.map((attribute) => (
          <article className="attribute-row" key={attribute.id} role="row">
            <span>
              <strong>{attribute.label}</strong>
              <small>{attribute.category}</small>
            </span>
            <code>{attribute.value || 'empty'}</code>
            <code>{attribute.path}</code>
            <small>{attribute.source}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

function ReuseResults({
  accepted,
  recommendations,
  setAccepted,
}: {
  accepted: Record<string, boolean>;
  recommendations: ReuseRecommendation[];
  setAccepted: (accepted: Record<string, boolean>) => void;
}) {
  if (!recommendations.length) {
    return <EmptyState text="Run reuse recommendation to map extracted requirements to DCAT, Construct-DCAT, AAS, BOT, IFC, or extension terms." />;
  }

  return (
    <div className="candidate-list">
      {recommendations.map((recommendation) => (
        <article className="recommendation-item" key={recommendation.id}>
          <label className="recommendation-toggle">
            <input
              checked={accepted[recommendation.id] !== false}
              onChange={(event) => setAccepted({ ...accepted, [recommendation.id]: event.target.checked })}
              type="checkbox"
            />
            <span>{recommendation.label}</span>
          </label>
          <code>{recommendation.term_uri}</code>
          <p>{recommendation.rationale}</p>
          <small>
            {recommendation.vocabulary} - priority {recommendation.priority} - {recommendation.action} - {formatConfidence(recommendation.confidence)}
          </small>
        </article>
      ))}
    </div>
  );
}

function SummaryStrip({ analysis }: { analysis: AnalysisResponse }) {
  return (
    <div className="summary-strip">
      <span>{analysis.artifacts.length} artifacts</span>
      <span>{analysis.requirements.length} requirements</span>
      <span>{analysis.metadata_candidates.length} metadata candidates</span>
      <span>{analysis.semantic_candidates.length} semantic candidates</span>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <p className="empty-state">{text}</p>;
}

function groupByCategory(requirements: CandidateRequirement[]) {
  return requirements.reduce<Record<string, CandidateRequirement[]>>((grouped, requirement) => {
    grouped[requirement.category] = [...(grouped[requirement.category] ?? []), requirement];
    return grouped;
  }, {});
}

function formatConfidence(confidence: number) {
  return `${Math.round(confidence * 100)}%`;
}

