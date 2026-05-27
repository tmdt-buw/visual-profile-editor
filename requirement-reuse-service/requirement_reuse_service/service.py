from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import re
import zipfile
from collections import Counter
from typing import Any, Iterable

from rdflib import Graph

from .models import (
    AnalysisRequest,
    AnalysisResponse,
    ArtifactPayload,
    ArtifactSummary,
    CandidateRequirement,
    CompetencyQuestion,
    ExtractedAttribute,
    ConstraintGenerationRequest,
    ConstraintGenerationResponse,
    MetadataCandidate,
    RecommendationRequest,
    RecommendationResponse,
    ReuseRecommendation,
    SemanticCandidate,
)


TEXT_RULES = [
    {
        'category': 'Dataset Metadata',
        'title': 'Describe datasets with reusable catalog metadata',
        'description': 'The artifact asks for dataset-level description, title, keywords, publisher, or thematic metadata.',
        'tokens': ['title', 'description', 'describe', 'keyword', 'theme', 'publisher', 'catalog', 'dataset metadata'],
        'properties': ['title', 'description', 'keyword', 'theme', 'publisher'],
    },
    {
        'category': 'Semantic Anchors',
        'title': 'Provide semantic anchors to external concepts',
        'description': 'The artifact refers to semantic IDs, ontology concepts, controlled terms, AAS submodels, IFC entities, or SKOS concepts.',
        'tokens': ['semantic', 'ontology', 'vocabulary', 'concept', 'skos', 'aas', 'submodel', 'semanticid', 'semantic id', 'ifc', 'bot'],
        'properties': ['semanticAnchor', 'usesOntology'],
    },
    {
        'category': 'Asset Semantics',
        'title': 'Capture construction asset semantics',
        'description': 'The artifact mentions construction assets, element types, systems, sensors, spaces, or equipment.',
        'tokens': ['wall', 'hvac', 'pump', 'sensor', 'asset', 'building element', 'space', 'zone', 'equipment', 'component'],
        'properties': ['describesAssetType'],
    },
    {
        'category': 'Lifecycle Information',
        'title': 'Represent construction lifecycle context',
        'description': 'The artifact indicates lifecycle phases such as design, construction, operation, or maintenance.',
        'tokens': ['planning', 'design', 'construction', 'operation', 'maintenance', 'demolition', 'lifecycle', 'life cycle'],
        'properties': ['hasLifecyclePhase'],
    },
    {
        'category': 'Technical Metadata',
        'title': 'Expose technical representation details',
        'description': 'The artifact asks for format, media type, schema version, distribution, or downloadable representation metadata.',
        'tokens': ['format', 'schema version', 'version', 'media type', 'download', 'distribution', 'json', 'rdf', 'ttl', 'ifc file', 'csv'],
        'properties': ['distribution', 'format', 'mediaType', 'schemaVersion', 'downloadURL'],
    },
    {
        'category': 'Access/Policy',
        'title': 'Capture access and policy conditions',
        'description': 'The artifact mentions license, rights, access URL, access rights, policy, or usage constraints.',
        'tokens': ['license', 'rights', 'access', 'policy', 'permission', 'restricted', 'usage'],
        'properties': ['license', 'accessRights', 'accessURL'],
    },
    {
        'category': 'Quality Metadata',
        'title': 'Capture provenance and quality metadata',
        'description': 'The artifact asks for provenance, completeness, confidence, quality, or source system information.',
        'tokens': ['provenance', 'complete', 'completeness', 'quality', 'confidence', 'source system', 'origin'],
        'properties': ['provenance', 'quality', 'hasDataSourceSystem'],
    },
]


PROPERTY_CATALOG: dict[str, dict[str, Any]] = {
    'title': {'label': 'Title', 'uri': 'http://purl.org/dc/terms/title', 'vocabulary': 'DCAT/DCAT-AP', 'range': 'string', 'level': 'mandatory', 'priority': 1},
    'description': {'label': 'Description', 'uri': 'http://purl.org/dc/terms/description', 'vocabulary': 'DCAT/DCAT-AP', 'range': 'string', 'level': 'recommended', 'priority': 1},
    'keyword': {'label': 'Keyword', 'uri': 'http://www.w3.org/ns/dcat#keyword', 'vocabulary': 'DCAT/DCAT-AP', 'range': 'string', 'level': 'recommended', 'priority': 1},
    'theme': {'label': 'Theme', 'uri': 'http://www.w3.org/ns/dcat#theme', 'vocabulary': 'DCAT/DCAT-AP', 'range': 'SkosConcept', 'level': 'recommended', 'priority': 1},
    'publisher': {'label': 'Publisher', 'uri': 'http://purl.org/dc/terms/publisher', 'vocabulary': 'DCAT/DCAT-AP', 'range': 'FoafAgent', 'level': 'recommended', 'priority': 1},
    'distribution': {'label': 'Distribution', 'uri': 'http://www.w3.org/ns/dcat#distribution', 'vocabulary': 'DCAT/DCAT-AP', 'range': 'DcatDistribution', 'level': 'recommended', 'priority': 1},
    'accessURL': {'label': 'Access URL', 'uri': 'http://www.w3.org/ns/dcat#accessURL', 'vocabulary': 'DCAT/DCAT-AP', 'range': 'anyURI', 'level': 'mandatory', 'priority': 1},
    'downloadURL': {'label': 'Download URL', 'uri': 'http://www.w3.org/ns/dcat#downloadURL', 'vocabulary': 'DCAT/DCAT-AP', 'range': 'anyURI', 'level': 'recommended', 'priority': 1},
    'mediaType': {'label': 'Media type', 'uri': 'http://www.w3.org/ns/dcat#mediaType', 'vocabulary': 'DCAT/DCAT-AP', 'range': 'string', 'level': 'recommended', 'priority': 1},
    'format': {'label': 'Format', 'uri': 'http://purl.org/dc/terms/format', 'vocabulary': 'DCAT/DCAT-AP', 'range': 'string', 'level': 'recommended', 'priority': 1},
    'license': {'label': 'License', 'uri': 'http://purl.org/dc/terms/license', 'vocabulary': 'DCAT/DCAT-AP', 'range': 'anyURI', 'level': 'recommended', 'priority': 1},
    'accessRights': {'label': 'Access rights', 'uri': 'http://purl.org/dc/terms/accessRights', 'vocabulary': 'DCAT/DCAT-AP', 'range': 'string', 'level': 'recommended', 'priority': 1},
    'provenance': {'label': 'Provenance', 'uri': 'http://purl.org/dc/terms/provenance', 'vocabulary': 'DCAT/DCAT-AP', 'range': 'string', 'level': 'optional', 'priority': 1},
    'semanticAnchor': {'label': 'Semantic anchor', 'uri': 'https://w3id.org/cx#semanticAnchor', 'vocabulary': 'Construct-DCAT', 'range': 'SemanticAnchor', 'level': 'mandatory', 'priority': 2},
    'usesOntology': {'label': 'Uses ontology', 'uri': 'https://w3id.org/cx#usesOntology', 'vocabulary': 'Construct-DCAT', 'range': 'anyURI', 'level': 'recommended', 'priority': 2},
    'hasLifecyclePhase': {'label': 'Lifecycle phase', 'uri': 'https://w3id.org/cx#hasLifecyclePhase', 'vocabulary': 'Construct-DCAT', 'range': 'LifecyclePhaseEnum', 'level': 'recommended', 'priority': 2},
    'describesAssetType': {'label': 'Describes asset type', 'uri': 'https://w3id.org/cx#describesAssetType', 'vocabulary': 'Construct-DCAT', 'range': 'ConstructionAsset', 'level': 'recommended', 'priority': 2},
    'hasAASSubmodel': {'label': 'AAS submodel anchor', 'uri': 'https://w3id.org/cx#hasAASSubmodel', 'vocabulary': 'AAS/Construct-DCAT', 'range': 'anyURI', 'level': 'recommended', 'priority': 3},
    'hasIFCEntity': {'label': 'IFC entity anchor', 'uri': 'https://w3id.org/cx#hasIFCEntity', 'vocabulary': 'IFC/Construct-DCAT', 'range': 'anyURI', 'level': 'recommended', 'priority': 3},
    'schemaVersion': {'label': 'Conforms to schema/version', 'uri': 'http://purl.org/dc/terms/conformsTo', 'vocabulary': 'DCAT/DCAT-AP', 'range': 'anyURI', 'level': 'recommended', 'priority': 1},
    'quality': {'label': 'Quality annotation', 'uri': 'https://w3id.org/cx#qualityAnnotation', 'vocabulary': 'Construct-DCAT extension', 'range': 'string', 'level': 'optional', 'priority': 4},
    'hasDataSourceSystem': {'label': 'Data source system', 'uri': 'https://w3id.org/cx#hasDataSourceSystem', 'vocabulary': 'Construct-DCAT', 'range': 'string', 'level': 'optional', 'priority': 2},
}


AAS_ATTRIBUTE_KEYS = {
    'id',
    'idshort',
    'semanticid',
    'semanticidlist',
    'modeltype',
    'category',
    'kind',
    'value',
    'valuetype',
    'preferredname',
    'shortname',
    'displayname',
    'description',
    'assetkind',
    'globalassetid',
    'idtype',
}

URI_TO_PROPERTY = {
    'http://purl.org/dc/terms/title': 'title',
    'http://purl.org/dc/terms/description': 'description',
    'http://purl.org/dc/terms/publisher': 'publisher',
    'http://purl.org/dc/terms/license': 'license',
    'http://purl.org/dc/terms/accessRights': 'accessRights',
    'http://purl.org/dc/terms/format': 'format',
    'http://purl.org/dc/terms/conformsTo': 'schemaVersion',
    'http://www.w3.org/ns/dcat#keyword': 'keyword',
    'http://www.w3.org/ns/dcat#theme': 'theme',
    'http://www.w3.org/ns/dcat#distribution': 'distribution',
    'http://www.w3.org/ns/dcat#accessURL': 'accessURL',
    'http://www.w3.org/ns/dcat#downloadURL': 'downloadURL',
    'http://www.w3.org/ns/dcat#mediaType': 'mediaType',
}


def analyze_payload(payload: AnalysisRequest) -> AnalysisResponse:
    artifacts: list[ArtifactSummary] = []
    requirements: list[CandidateRequirement] = []
    semantic_candidates: list[SemanticCandidate] = []
    metadata_candidates: list[MetadataCandidate] = []
    competency_questions: list[CompetencyQuestion] = []
    extracted_attributes: list[ExtractedAttribute] = []

    if payload.text and payload.text.strip():
        summary, reqs, sem, meta, questions, attrs = analyze_text('text description', payload.text)
        artifacts.append(summary)
        requirements.extend(reqs)
        semantic_candidates.extend(sem)
        metadata_candidates.extend(meta)
        competency_questions.extend(questions)
        extracted_attributes.extend(attrs)

    for artifact in payload.artifacts:
        summary, reqs, sem, meta, questions, attrs = analyze_artifact(artifact)
        artifacts.append(summary)
        requirements.extend(reqs)
        semantic_candidates.extend(sem)
        metadata_candidates.extend(meta)
        competency_questions.extend(questions)
        extracted_attributes.extend(attrs)

    return AnalysisResponse(
        artifacts=artifacts,
        extracted_attributes=dedupe_attributes(extracted_attributes),
        requirements=dedupe_requirements(requirements),
        semantic_candidates=dedupe_semantic(semantic_candidates),
        metadata_candidates=dedupe_metadata(metadata_candidates),
        competency_questions=dedupe_questions(competency_questions),
    )


def extract_requirements(payload: AnalysisRequest) -> AnalysisResponse:
    analysis = analyze_payload(payload)
    return AnalysisResponse(
        artifacts=analysis.artifacts,
        extracted_attributes=analysis.extracted_attributes,
        requirements=analysis.requirements,
        semantic_candidates=analysis.semantic_candidates,
        metadata_candidates=analysis.metadata_candidates,
        competency_questions=analysis.competency_questions,
    )


def recommend_reuse(payload: RecommendationRequest) -> RecommendationResponse:
    requirements = list(payload.requirements)
    semantic_candidates = list(payload.semantic_candidates)
    metadata_candidates = list(payload.metadata_candidates)
    if payload.analysis:
        requirements.extend(payload.analysis.requirements)
        semantic_candidates.extend(payload.analysis.semantic_candidates)
        metadata_candidates.extend(payload.analysis.metadata_candidates)

    recommendations: list[ReuseRecommendation] = []
    extension_candidates: list[MetadataCandidate] = []

    for candidate in dedupe_metadata(metadata_candidates):
        term = PROPERTY_CATALOG.get(candidate.property)
        if not term:
            extension_candidates.append(candidate)
            continue
        recommendations.append(recommendation_from_property(candidate.property, candidate_id=candidate.id, confidence=candidate.confidence, reason=f"Matched extracted metadata candidate '{candidate.label}' in {candidate.category}."))

    for requirement in dedupe_requirements(requirements):
        for prop in properties_for_category(requirement.category):
            recommendations.append(recommendation_from_property(prop, requirement_id=requirement.id, confidence=requirement.confidence, reason=f"Supports requirement category '{requirement.category}'."))

    for semantic in dedupe_semantic(semantic_candidates):
        lowered = f'{semantic.kind} {semantic.label} {semantic.identifier or ""}'.lower()
        if 'aas' in lowered or 'submodel' in lowered or 'semanticid' in lowered or 'semantic id' in lowered:
            recommendations.append(recommendation_from_property('hasAASSubmodel', candidate_id=semantic.id, confidence=semantic.confidence, reason='Reuse an AAS semantic identifier as a dataset semantic anchor.'))
        if 'ifc' in lowered:
            recommendations.append(recommendation_from_property('hasIFCEntity', candidate_id=semantic.id, confidence=semantic.confidence, reason='Reuse IFC class or schema evidence as a lightweight discovery anchor.'))
        if any(token in lowered for token in ['wall', 'space', 'sensor', 'pump', 'hvac', 'asset', 'element']):
            recommendations.append(recommendation_from_property('describesAssetType', candidate_id=semantic.id, confidence=semantic.confidence, reason='Map asset concepts to a reusable construction asset profile term.'))

    if not recommendations:
        for prop in ['title', 'description', 'keyword', 'distribution', 'semanticAnchor']:
            recommendations.append(recommendation_from_property(prop, reason='Baseline Construct-DCAT discovery profile recommendation.'))

    return RecommendationResponse(recommendations=dedupe_recommendations(recommendations), extension_candidates=extension_candidates)


def generate_constraints(payload: ConstraintGenerationRequest) -> ConstraintGenerationResponse:
    selected = set(payload.selected_recommendation_ids)
    recommendations = [item for item in payload.recommendations if not selected or item.id in selected]
    if not recommendations:
        recommendations = recommend_reuse(RecommendationRequest(analysis=payload.analysis, requirements=payload.requirements)).recommendations

    property_shapes = []
    slots: dict[str, Any] = {}
    slot_names: list[str] = []
    notes: list[str] = ['Review generated SHACL before using it as a normative profile artifact.']

    for rec in recommendations:
        slot_name = slot_name_from_uri(rec.term_uri)
        if slot_name not in slot_names:
            slot_names.append(slot_name)
        term = term_for_uri(rec.term_uri)
        required = rec.priority <= 2 and slot_name in {'title', 'accessURL', 'semanticAnchor'}
        level = 'mandatory' if required else 'recommended' if rec.priority <= 2 else 'optional'
        slots[slot_name] = {
            'title': rec.label,
            'slot_uri': compact_uri(rec.term_uri),
            'range': range_for_term(term, rec.term_uri),
            'required': True if required else None,
            'multivalued': True if slot_name in {'keyword', 'theme', 'distribution', 'semanticAnchor', 'usesOntology', 'hasAASSubmodel', 'hasIFCEntity'} else None,
            'annotations': {
                'term_kind': {'value': 'profile' if rec.action != 'extension' else 'extension'},
                'source_vocabulary': {'value': rec.vocabulary},
                'requirement_level': {'value': level},
                'recommendation_rationale': {'value': rec.rationale},
            },
        }

        severity = 'sh:Violation' if required else 'sh:Warning'
        min_count = '\n        sh:minCount 1 ;' if required else ''
        property_shapes.append(
            f'''    sh:property [
        sh:path {compact_uri(rec.term_uri)} ;{min_count}
        sh:severity {severity} ;
        sh:message "Review {rec.label} for Construct-DCAT discovery metadata." ;
    ] ;'''
        )

    for slot_def in slots.values():
        if slot_def.get('required') is None:
            slot_def.pop('required', None)
        if slot_def.get('multivalued') is None:
            slot_def.pop('multivalued', None)

    shacl = '''@prefix cx: <https://w3id.org/cx#> .
@prefix dcat: <http://www.w3.org/ns/dcat#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix sh: <http://www.w3.org/ns/shacl#> .

cx:ConstructionDatasetRequirementShape
    a sh:NodeShape ;
    sh:targetClass dcat:Dataset ;
''' + '\n'.join(property_shapes).rstrip(' ;') + ' .\n'

    profile_draft = {
        'id': 'https://w3id.org/construct-dcat/profile/generated-requirements',
        'name': 'generated_requirement_profile',
        'title': 'Generated Requirement Profile Draft',
        'description': 'Human-reviewed draft generated from requirement extraction and reuse recommendations.',
        'prefixes': {
            'linkml': 'https://w3id.org/linkml/',
            'dcat': 'http://www.w3.org/ns/dcat#',
            'dcterms': 'http://purl.org/dc/terms/',
            'cx': 'https://w3id.org/cx#',
            'skos': 'http://www.w3.org/2004/02/skos/core#',
            'foaf': 'http://xmlns.com/foaf/0.1/',
            'prov': 'http://www.w3.org/ns/prov#',
        },
        'imports': ['linkml:types'],
        'default_prefix': 'cx',
        'default_range': 'string',
        'classes': {
            'GeneratedConstructionDatasetProfile': {
                'title': 'Generated Construction Dataset Profile',
                'is_a': 'DcatDataset',
                'class_uri': 'cx:GeneratedConstructionDatasetProfile',
                'slots': slot_names,
                'annotations': {
                    'term_kind': {'value': 'profile'},
                    'profile_of': {'value': 'dcat:Dataset'},
                    'requirement_level': {'value': 'recommended'},
                },
            }
        },
        'slots': slots,
        'enums': {},
    }

    return ConstraintGenerationResponse(shacl=shacl, profile_draft=profile_draft, validation_notes=notes)


def analyze_artifact(artifact: ArtifactPayload):
    kind = detect_kind(artifact)
    if kind == 'aasx':
        return analyze_aasx(artifact.name, artifact)

    content = decode_artifact_text(artifact)
    if kind == 'aas-json':
        return analyze_aas_json(artifact.name, content)
    if kind == 'dcat-rdf':
        return analyze_dcat_metadata(artifact.name, content)
    if kind == 'ifc':
        return analyze_ifc(artifact.name, content)
    return analyze_text(artifact.name, content)



def analyze_aasx(source: str, artifact: ArtifactPayload):
    try:
        raw = decode_artifact_bytes(artifact)
    except ValueError as exc:
        summary = ArtifactSummary(name=source, kind='aasx', evidence_count=0, notes=[str(exc)])
        return summary, [], [], [], [], []

    requirements: list[CandidateRequirement] = []
    semantic_candidates: list[SemanticCandidate] = []
    metadata_candidates: list[MetadataCandidate] = []
    questions: list[CompetencyQuestion] = []
    extracted_attributes: list[ExtractedAttribute] = []
    notes: list[str] = []
    embedded_count = 0

    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as package:
            names = [name for name in package.namelist() if not name.endswith('/')]
            notes.append(f'{len(names)} package entries')

            for name in names:
                lowered = name.lower()
                if not lowered.endswith(('.json', '.xml', '.aas')):
                    continue

                try:
                    payload = package.read(name)
                except KeyError:
                    continue
                text = payload.decode('utf-8', errors='replace')

                if lowered.endswith(('.json', '.aas')):
                    try:
                        json.loads(text)
                    except json.JSONDecodeError:
                        continue
                    summary, reqs, sem, meta, qs, attrs = analyze_aas_json(f'{source}:{name}', text)
                    if summary.evidence_count:
                        embedded_count += 1
                        requirements.extend(reqs)
                        semantic_candidates.extend(sem)
                        metadata_candidates.extend(meta)
                        questions.extend(qs)
                        extracted_attributes.extend(attrs)
                    continue

                summary, reqs, sem, meta, qs, attrs = analyze_aas_xml(f'{source}:{name}', text)
                if summary.evidence_count:
                    embedded_count += 1
                    requirements.extend(reqs)
                    semantic_candidates.extend(sem)
                    metadata_candidates.extend(meta)
                    questions.extend(qs)
                    extracted_attributes.extend(attrs)
    except zipfile.BadZipFile:
        fallback = decode_artifact_text(artifact)
        summary, reqs, sem, meta, qs, attrs = analyze_text(source, fallback)
        summary.kind = 'aasx'
        summary.notes.append('AASX package could not be opened as ZIP; scanned decoded text fallback.')
        return summary, reqs, sem, meta, qs, attrs

    if embedded_count:
        notes.append(f'{embedded_count} embedded AAS payload(s) analyzed')
    else:
        notes.append('No parseable embedded AAS JSON/XML payload found')

    summary = ArtifactSummary(
        name=source,
        kind='aasx',
        evidence_count=sum(len(item.evidence) for item in semantic_candidates),
        notes=notes,
    )
    return summary, requirements, semantic_candidates, metadata_candidates, questions, dedupe_attributes(extracted_attributes)


def analyze_aas_xml(source: str, content: str):
    idshorts = clean_matches(re.findall(r'<(?:[A-Za-z0-9_]+:)?idShort[^>]*>\s*([^<]+)', content, flags=re.IGNORECASE))
    identifiers = clean_matches(
        re.findall(r'(?:https?://[^\s<>"\']+|urn:[^\s<>"\']+|irdi:[^\s<>"\']+|0173-[^\s<>"\']+)', content)
    )
    concept_labels = clean_matches(
        re.findall(r'<(?:[A-Za-z0-9_]+:)?preferredName[^>]*>\s*([^<]+)', content, flags=re.IGNORECASE)
    )

    if not idshorts and not identifiers and not concept_labels and 'submodel' not in content.lower():
        return ArtifactSummary(name=source, kind='aas-xml', evidence_count=0, notes=[]), [], [], [], [], []

    requirements = [
        CandidateRequirement(
            id=stable_id('req', source, 'aas-xml-semantic-anchors'),
            title='Reuse AAS package identifiers as metadata anchors',
            description='AASX packages can contribute submodels, idShort values, concept descriptions, and semantic identifiers as discovery-level anchors.',
            category='Semantic Anchors',
            source=source,
            evidence=['AAS XML payload detected in AASX package'],
            confidence=0.82,
        )
    ]
    metadata_candidates = [
        metadata_candidate('semanticAnchor', 'Semantic Anchors', source, 'AASX package payload detected', 0.82),
        metadata_candidate('hasAASSubmodel', 'Semantic Anchors', source, 'AASX package payload detected', 0.8),
        metadata_candidate('hasDataSourceSystem', 'Quality Metadata', source, 'AASX package source', 0.64),
    ]

    semantic_candidates: list[SemanticCandidate] = []
    extracted_attributes: list[ExtractedAttribute] = []
    for index, value in enumerate(idshorts[:80]):
        extracted_attributes.append(extracted_attribute(source, f'//idShort[{index}]', 'idShort', value, 'AAS Attribute', 0.82))
    for index, value in enumerate(identifiers[:80]):
        extracted_attributes.append(extracted_attribute(source, f'//semanticId[{index}]', 'semanticId', value, 'Semantic Anchor', 0.82))
    for index, value in enumerate(concept_labels[:80]):
        extracted_attributes.append(extracted_attribute(source, f'//preferredName[{index}]', 'preferredName', value, 'AAS Attribute', 0.78))

    for label, kind in (
        [(item, 'xml-idShort') for item in idshorts[:40]]
        + [(item, 'semantic-id') for item in identifiers[:40]]
        + [(item, 'concept-description') for item in concept_labels[:40]]
    ):
        semantic_candidates.append(
            SemanticCandidate(
                id=stable_id('sem', source, kind, label),
                label=label,
                kind=f'aas-{kind}',
                identifier=label if looks_like_uri(label) else None,
                source=source,
                evidence=[kind],
                confidence=0.78,
            )
        )

    notes = [f'{len(idshorts)} idShort values', f'{len(identifiers)} semantic identifiers', f'{len(concept_labels)} concept labels']
    questions = [generated_question('Semantic Anchors', source), generated_question('Dataset Metadata', source)]
    return ArtifactSummary(name=source, kind='aas-xml', evidence_count=len(semantic_candidates), notes=notes), requirements, semantic_candidates, metadata_candidates, questions, dedupe_attributes(extracted_attributes)


def analyze_text(source: str, text: str):
    requirements: list[CandidateRequirement] = []
    semantic_candidates: list[SemanticCandidate] = []
    metadata_candidates: list[MetadataCandidate] = []
    questions: list[CompetencyQuestion] = []
    evidence_count = 0

    sentences = split_sentences(text)
    for sentence in sentences:
        lowered = sentence.lower()
        for rule in TEXT_RULES:
            if any(token in lowered for token in rule['tokens']):
                evidence_count += 1
                req_id = stable_id('req', rule['category'], rule['title'], source)
                requirements.append(CandidateRequirement(id=req_id, title=rule['title'], description=rule['description'], category=rule['category'], source=source, evidence=[sentence], confidence=0.7))
                for prop in rule['properties']:
                    metadata_candidates.append(metadata_candidate(prop, rule['category'], source, sentence, 0.72))
        if sentence.endswith('?'):
            questions.append(CompetencyQuestion(id=stable_id('cq', source, sentence), question=sentence, category=infer_category(sentence), source=source, evidence=sentence))

    for concept in re.findall(r'\b(?:IFC[A-Z][A-Za-z0-9]+|AAS|BOT|HVAC|BIM|wall|pump|sensor|submodel|semantic ID)\b', text, flags=re.IGNORECASE):
        semantic_candidates.append(SemanticCandidate(id=stable_id('sem', source, concept), label=concept, kind='domain-concept', source=source, evidence=[concept], confidence=0.68))

    for category in sorted({item.category for item in requirements}):
        questions.append(generated_question(category, source))

    return ArtifactSummary(name=source, kind='text', evidence_count=evidence_count, notes=['Text requirements scanned with rule-based discovery heuristics.']), requirements, semantic_candidates, metadata_candidates, questions, []


def analyze_aas_json(source: str, content: str):
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return analyze_text(source, content)

    requirements = [
        CandidateRequirement(
            id=stable_id('req', source, 'aas-semantic-anchors'),
            title='Reuse AAS semantic identifiers as metadata anchors',
            description='AAS submodels, semantic IDs, concept descriptions, and idShort values can support discovery-level semantic anchoring.',
            category='Semantic Anchors',
            source=source,
            evidence=['AAS JSON structure detected'],
            confidence=0.88,
        )
    ]
    semantic_candidates: list[SemanticCandidate] = []
    metadata_candidates = [
        metadata_candidate('semanticAnchor', 'Semantic Anchors', source, 'AAS JSON structure detected', 0.86),
        metadata_candidate('hasAASSubmodel', 'Semantic Anchors', source, 'AAS JSON structure detected', 0.84),
        metadata_candidate('hasDataSourceSystem', 'Quality Metadata', source, 'AAS JSON source system', 0.66),
    ]

    idshorts: list[str] = []
    identifiers: list[str] = []
    concept_labels: list[str] = []
    extracted_attributes: list[ExtractedAttribute] = []

    def walk(value: Any, path: str = '$') -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                key_label = str(key)
                key_norm = key_label.lower()
                child_path = f'{path}.{key_label}'
                if key_norm in AAS_ATTRIBUTE_KEYS:
                    if key_norm in {'semanticid', 'semanticidlist'}:
                        extracted = extract_identifiers(child)
                        identifiers.extend(extracted)
                        for index, identifier in enumerate(extracted[:20]):
                            extracted_attributes.append(extracted_attribute(source, f'{child_path}[{index}]', key_label, identifier, 'Semantic Anchor', 0.86))
                    elif key_norm in {'preferredname', 'displayname', 'description', 'modeltype'}:
                        labels = extract_labels(child)
                        if key_norm == 'preferredname':
                            concept_labels.extend(labels)
                        for index, label in enumerate(labels[:20]):
                            extracted_attributes.append(extracted_attribute(source, f'{child_path}[{index}]', key_label, label, 'AAS Attribute', 0.78))
                    elif is_scalar(child):
                        if key_norm == 'idshort':
                            idshorts.append(str(child))
                        if key_norm == 'id' and ('submodel' in path.lower() or 'concept' in path.lower()):
                            identifiers.append(str(child))
                        extracted_attributes.append(extracted_attribute(source, child_path, key_label, child, 'AAS Attribute', 0.78))
                walk(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f'{path}[{index}]')

    walk(data)

    for label, kind in [(item, 'idShort') for item in idshorts[:40]] + [(item, 'semantic-id') for item in identifiers[:40]] + [(item, 'concept-description') for item in concept_labels[:40]]:
        semantic_candidates.append(SemanticCandidate(id=stable_id('sem', source, kind, label), label=label, kind=f'aas-{kind}', identifier=label if looks_like_uri(label) else None, source=source, evidence=[kind], confidence=0.82))

    notes = [f'{len(idshorts)} idShort values', f'{len(identifiers)} semantic identifiers', f'{len(concept_labels)} concept labels']
    questions = [generated_question('Semantic Anchors', source), generated_question('Dataset Metadata', source)]
    return ArtifactSummary(name=source, kind='aas-json', evidence_count=len(idshorts) + len(identifiers) + len(concept_labels), notes=notes), requirements, semantic_candidates, metadata_candidates, questions, dedupe_attributes(extracted_attributes)


def analyze_dcat_metadata(source: str, content: str):
    requirements: list[CandidateRequirement] = []
    semantic_candidates: list[SemanticCandidate] = []
    metadata_candidates: list[MetadataCandidate] = []
    questions: list[CompetencyQuestion] = []
    predicates: Counter[str] = Counter()
    extracted_attributes: list[ExtractedAttribute] = []

    parsed = False
    for fmt in ['turtle', 'json-ld', 'xml', 'nt']:
        graph = Graph()
        try:
            graph.parse(data=content, format=fmt)
        except Exception:
            continue
        for subject, predicate, obj in graph:
            predicates[str(predicate)] += 1
            extracted_attributes.append(extracted_attribute(source, str(predicate), str(predicate).rsplit('/', 1)[-1].rsplit('#', 1)[-1], str(obj), 'RDF Metadata', 0.76))
            if looks_like_uri(str(obj)) and any(token in str(obj).lower() for token in ['ifc', 'aas', 'bot', 'skos', 'w3id']):
                semantic_candidates.append(SemanticCandidate(id=stable_id('sem', source, str(obj)), label=str(obj).rsplit('/', 1)[-1], kind='linked-resource', identifier=str(obj), source=source, evidence=[str(predicate)], confidence=0.78))
        parsed = True
        break

    if not parsed:
        try:
            data = json.loads(content)
            for key in collect_keys(data):
                predicates[key] += 1
            extracted_attributes.extend(collect_json_attributes(source, data, '$', limit=160))
        except json.JSONDecodeError:
            return analyze_text(source, content)

    for predicate, count in predicates.most_common():
        prop = URI_TO_PROPERTY.get(predicate) or key_to_property(predicate)
        if prop:
            metadata_candidates.append(metadata_candidate(prop, 'Dataset Metadata' if prop in {'title', 'description', 'keyword', 'theme', 'publisher'} else 'Technical Metadata', source, f'{predicate} used {count} time(s)', 0.8))

    if metadata_candidates:
        requirements.append(CandidateRequirement(id=stable_id('req', source, 'reuse-existing-dcat-patterns'), title='Reuse existing DCAT metadata patterns', description='Existing metadata examples contain properties that can seed a reusable profile.', category='Dataset Metadata', source=source, evidence=[item.label for item in metadata_candidates[:6]], confidence=0.82))
    questions.append(generated_question('Dataset Metadata', source))
    return ArtifactSummary(name=source, kind='dcat-rdf', evidence_count=sum(predicates.values()), notes=[f'{len(predicates)} unique metadata predicates or keys']), requirements, semantic_candidates, metadata_candidates, questions, dedupe_attributes(extracted_attributes)


def analyze_ifc(source: str, content: str):
    schema_match = re.search(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'", content, flags=re.IGNORECASE)
    schema = schema_match.group(1) if schema_match else 'IFC'
    classes = Counter(match.upper() for match in re.findall(r'\bIFC[A-Z][A-Z0-9_]*\b', content, flags=re.IGNORECASE))
    psets = Counter(match for match in re.findall(r'\bPset_[A-Za-z0-9_]+', content))

    requirements = [
        CandidateRequirement(id=stable_id('req', source, 'ifc-discovery'), title='Expose lightweight IFC discovery metadata', description='IFC artifacts should contribute schema version, entity class, and property set statistics as metadata requirements.', category='Technical Metadata', source=source, evidence=[schema], confidence=0.8),
        CandidateRequirement(id=stable_id('req', source, 'ifc-anchors'), title='Use IFC classes as semantic anchors', description='Frequent IFC classes can be reused as discovery-level semantic anchors without transforming the full model.', category='Semantic Anchors', source=source, evidence=[name for name, _ in classes.most_common(8)], confidence=0.78),
    ]
    metadata_candidates = [
        metadata_candidate('schemaVersion', 'Technical Metadata', source, schema, 0.8),
        metadata_candidate('hasIFCEntity', 'Semantic Anchors', source, ', '.join(name for name, _ in classes.most_common(5)), 0.78),
        metadata_candidate('describesAssetType', 'Asset Semantics', source, ', '.join(name for name, _ in classes.most_common(5)), 0.7),
    ]
    semantic_candidates = [
        SemanticCandidate(id=stable_id('sem', source, name), label=name, kind='ifc-class', identifier=f'https://standards.buildingsmart.org/IFC/DEV/IFC4/ADD2_TC1/OWL#{name.title()}', source=source, evidence=[f'{count} occurrence(s)'], confidence=min(0.9, 0.65 + count / 100))
        for name, count in classes.most_common(30)
    ]
    extracted_attributes = [extracted_attribute(source, 'FILE_SCHEMA', 'FILE_SCHEMA', schema, 'IFC Metadata', 0.82)]
    extracted_attributes.extend(extracted_attribute(source, f'IFC_CLASS[{name}]', name, str(count), 'IFC Class Count', min(0.9, 0.65 + count / 100), 'count') for name, count in classes.most_common(80))
    extracted_attributes.extend(extracted_attribute(source, f'PSET[{name}]', name, str(count), 'IFC Property Set Count', 0.7, 'count') for name, count in psets.most_common(80))
    questions = [generated_question('Semantic Anchors', source), generated_question('Technical Metadata', source)]
    notes = [f'Schema: {schema}', f'{len(classes)} IFC classes', f'{len(psets)} property set references']
    return ArtifactSummary(name=source, kind='ifc', evidence_count=sum(classes.values()) + sum(psets.values()), notes=notes), requirements, semantic_candidates, metadata_candidates, questions, dedupe_attributes(extracted_attributes)


def detect_kind(artifact: ArtifactPayload) -> str:
    name = artifact.name.lower()
    media = (artifact.media_type or '').lower()
    if name.endswith('.aasx') or media in {'application/asset-administration-shell-package', 'application/aasx'}:
        return 'aasx'

    content = decode_artifact_text(artifact).lstrip()[:600].lower()
    if name.endswith(('.ifc', '.ifcspf')) or 'iso-10303-21' in content or 'file_schema' in content:
        return 'ifc'
    if name.endswith(('.ttl', '.rdf', '.owl', '.jsonld', '.nt')) or '@prefix' in content or 'dcat:' in content or 'http://www.w3.org/ns/dcat' in content:
        return 'dcat-rdf'
    if name.endswith('.json') or 'json' in media:
        try:
            data = json.loads(decode_artifact_text(artifact))
        except json.JSONDecodeError:
            return 'text'
        keys = {key.lower() for key in collect_keys(data)}
        if {'submodels', 'semanticid', 'conceptdescriptions', 'idshort'} & keys:
            return 'aas-json'
        if any('dcat' in key or '@type' == key for key in keys):
            return 'dcat-rdf'
    return 'text'



def decode_artifact_bytes(artifact: ArtifactPayload) -> bytes:
    if artifact.content_encoding == 'base64':
        try:
            return base64.b64decode(artifact.content, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f'Artifact {artifact.name} is not valid base64 content') from exc
    return artifact.content.encode('utf-8', errors='replace')


def decode_artifact_text(artifact: ArtifactPayload) -> str:
    if artifact.content_encoding == 'base64':
        try:
            return decode_artifact_bytes(artifact).decode('utf-8', errors='replace')
        except ValueError:
            return ''
    return artifact.content or ''


def clean_matches(values: Iterable[str]) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        item = re.sub(r'\s+', ' ', value).strip()
        if item and item not in cleaned:
            cleaned.append(item)
    return cleaned



def extracted_attribute(source: str, path: str, label: str, value: Any, category: str, confidence: float = 0.7, value_type: str = 'string') -> ExtractedAttribute:
    text = attribute_value(value)
    return ExtractedAttribute(
        id=stable_id('attr', source, path, label, text),
        source=source,
        path=path,
        label=label,
        value=text,
        category=category,
        value_type=value_type,
        confidence=confidence,
    )


def collect_json_attributes(source: str, value: Any, path: str = '$', limit: int = 120) -> list[ExtractedAttribute]:
    attributes: list[ExtractedAttribute] = []

    def walk(current: Any, current_path: str) -> None:
        if len(attributes) >= limit:
            return
        if isinstance(current, dict):
            for key, child in current.items():
                child_path = f'{current_path}.{key}'
                if is_scalar(child):
                    attributes.append(extracted_attribute(source, child_path, str(key), child, 'JSON Metadata', 0.68))
                else:
                    walk(child, child_path)
        elif isinstance(current, list):
            for index, child in enumerate(current):
                walk(child, f'{current_path}[{index}]')

    walk(value, path)
    return attributes


def is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def attribute_value(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, (str, int, float, bool)):
        text = str(value)
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except TypeError:
            text = str(value)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:500]


def metadata_candidate(prop: str, category: str, source: str, evidence: str, confidence: float) -> MetadataCandidate:
    term = PROPERTY_CATALOG.get(prop, {'label': prop, 'range': 'string', 'level': 'recommended'})
    return MetadataCandidate(id=stable_id('meta', source, prop, category), property=prop, label=term['label'], category=category, range=term.get('range', 'string'), requirement_level=term.get('level', 'recommended'), source=source, evidence=[evidence], confidence=confidence)


def recommendation_from_property(prop: str, requirement_id: str | None = None, candidate_id: str | None = None, confidence: float = 0.65, reason: str = '') -> ReuseRecommendation:
    term = PROPERTY_CATALOG[prop]
    action = 'reuse' if term['priority'] == 1 else 'profile' if term['priority'] <= 3 else 'extension'
    return ReuseRecommendation(id=stable_id('rec', prop, requirement_id or '', candidate_id or ''), label=term['label'], vocabulary=term['vocabulary'], term_uri=term['uri'], priority=term['priority'], action=action, requirement_id=requirement_id, candidate_id=candidate_id, rationale=reason or f"Reuse {term['label']} from {term['vocabulary']}.", confidence=confidence)


def properties_for_category(category: str) -> list[str]:
    return {
        'Dataset Metadata': ['title', 'description', 'keyword', 'theme'],
        'Semantic Anchors': ['semanticAnchor', 'usesOntology'],
        'Asset Semantics': ['describesAssetType'],
        'Lifecycle Information': ['hasLifecyclePhase'],
        'Technical Metadata': ['distribution', 'format', 'mediaType', 'schemaVersion'],
        'Access/Policy': ['license', 'accessRights', 'accessURL'],
        'Quality Metadata': ['provenance', 'hasDataSourceSystem'],
    }.get(category, ['description'])


def split_sentences(text: str) -> list[str]:
    parts = re.split(r'(?<=[.!?])\s+|\n+', text)
    return [part.strip(' -*\t') for part in parts if part.strip(' -*\t')]


def infer_category(text: str) -> str:
    lowered = text.lower()
    for rule in TEXT_RULES:
        if any(token in lowered for token in rule['tokens']):
            return rule['category']
    return 'Dataset Metadata'


def generated_question(category: str, source: str) -> CompetencyQuestion:
    question = {
        'Dataset Metadata': 'Which datasets can be discovered by title, description, keyword, theme, publisher, and distribution metadata?',
        'Semantic Anchors': 'Which datasets are connected to reusable ontology terms, AAS semantic IDs, IFC classes, or controlled concepts?',
        'Asset Semantics': 'Which datasets describe a given construction asset type or building system?',
        'Lifecycle Information': 'Which datasets are relevant to a specific construction lifecycle phase?',
        'Technical Metadata': 'Which datasets are available in a specific format, schema version, or distribution form?',
        'Access/Policy': 'Which datasets can be reused under a given license, rights statement, or access policy?',
        'Quality Metadata': 'Which datasets provide provenance, completeness, quality, or source-system evidence?',
    }.get(category, 'Which datasets satisfy this metadata requirement?')
    return CompetencyQuestion(id=stable_id('cq', category, source), question=question, category=category, source=source)


def collect_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.append(str(key))
            keys.extend(collect_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(collect_keys(child))
    return keys


def extract_identifiers(value: Any) -> list[str]:
    identifiers: list[str] = []
    if isinstance(value, str):
        identifiers.append(value)
    elif isinstance(value, dict):
        for key in ['value', 'id', 'href', 'IRI', 'iri']:
            if isinstance(value.get(key), str):
                identifiers.append(value[key])
        for child in value.values():
            identifiers.extend(extract_identifiers(child))
    elif isinstance(value, list):
        for child in value:
            identifiers.extend(extract_identifiers(child))
    return clean_matches(identifiers)


def extract_labels(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        for key in ['text', 'value', 'preferredName', 'shortName']:
            if isinstance(value.get(key), str):
                return [value[key]]
        return [str(item) for key, item in value.items() if key.lower() not in {'language', 'lang'} and isinstance(item, str)]
    if isinstance(value, list):
        labels: list[str] = []
        for item in value:
            labels.extend(extract_labels(item))
        return clean_matches(labels)
    return []


def key_to_property(key: str) -> str | None:
    lowered = key.lower()
    mapping = {
        'title': 'title',
        'description': 'description',
        'keyword': 'keyword',
        'theme': 'theme',
        'publisher': 'publisher',
        'distribution': 'distribution',
        'accessurl': 'accessURL',
        'downloadurl': 'downloadURL',
        'mediatype': 'mediaType',
        'format': 'format',
        'license': 'license',
        'accessrights': 'accessRights',
        'conformsto': 'schemaVersion',
    }
    normalized = lowered.replace(':', '').replace('_', '').replace('-', '')
    return mapping.get(normalized)


def stable_id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha1('|'.join(str(part) for part in parts).encode('utf-8')).hexdigest()[:10]
    return f'{prefix}-{digest}'


def looks_like_uri(value: str) -> bool:
    return value.startswith(('http://', 'https://', 'urn:', 'irdi:', '0173-'))


def compact_uri(uri: str) -> str:
    prefixes = {
        'http://purl.org/dc/terms/': 'dcterms:',
        'http://www.w3.org/ns/dcat#': 'dcat:',
        'https://w3id.org/cx#': 'cx:',
        'http://www.w3.org/2004/02/skos/core#': 'skos:',
        'http://www.w3.org/ns/prov#': 'prov:',
    }
    for base, prefix in prefixes.items():
        if uri.startswith(base):
            return prefix + uri.removeprefix(base)
    return f'<{uri}>'


def slot_name_from_uri(uri: str) -> str:
    local = re.split(r'[#/]', uri.rstrip('/'))[-1]
    if local:
        return local[:1].lower() + local[1:]
    return 'generatedSlot'


def term_for_uri(uri: str) -> dict[str, Any] | None:
    for term in PROPERTY_CATALOG.values():
        if term['uri'] == uri:
            return term
    return None


def range_for_term(term: dict[str, Any] | None, uri: str) -> str:
    if term:
        return term.get('range', 'string')
    if uri.startswith(('http://', 'https://')):
        return 'anyURI'
    return 'string'


def dedupe_attributes(items: Iterable[ExtractedAttribute]) -> list[ExtractedAttribute]:
    grouped: dict[tuple[str, str, str], ExtractedAttribute] = {}
    for item in items:
        key = (item.source, item.path, item.value)
        if key not in grouped:
            grouped[key] = item
        else:
            grouped[key].confidence = max(grouped[key].confidence, item.confidence)
    return sorted(grouped.values(), key=lambda item: (item.source, item.category, item.path))[:300]


def dedupe_requirements(items: Iterable[CandidateRequirement]) -> list[CandidateRequirement]:
    grouped: dict[tuple[str, str], CandidateRequirement] = {}
    for item in items:
        key = (item.category, item.title)
        if key not in grouped:
            grouped[key] = item
        else:
            grouped[key].evidence = merge_evidence(grouped[key].evidence, item.evidence)
            grouped[key].confidence = max(grouped[key].confidence, item.confidence)
    return sorted(grouped.values(), key=lambda item: (item.category, item.title))


def dedupe_metadata(items: Iterable[MetadataCandidate]) -> list[MetadataCandidate]:
    grouped: dict[tuple[str, str], MetadataCandidate] = {}
    for item in items:
        key = (item.property, item.category)
        if key not in grouped:
            grouped[key] = item
        else:
            grouped[key].evidence = merge_evidence(grouped[key].evidence, item.evidence)
            grouped[key].confidence = max(grouped[key].confidence, item.confidence)
    return sorted(grouped.values(), key=lambda item: (item.category, item.property))


def dedupe_semantic(items: Iterable[SemanticCandidate]) -> list[SemanticCandidate]:
    grouped: dict[tuple[str, str], SemanticCandidate] = {}
    for item in items:
        key = (item.kind, item.identifier or item.label.lower())
        if key not in grouped:
            grouped[key] = item
        else:
            grouped[key].evidence = merge_evidence(grouped[key].evidence, item.evidence)
            grouped[key].confidence = max(grouped[key].confidence, item.confidence)
    return sorted(grouped.values(), key=lambda item: (item.kind, item.label))[:80]


def dedupe_questions(items: Iterable[CompetencyQuestion]) -> list[CompetencyQuestion]:
    seen: set[str] = set()
    result: list[CompetencyQuestion] = []
    for item in items:
        if item.question not in seen:
            seen.add(item.question)
            result.append(item)
    return result


def dedupe_recommendations(items: Iterable[ReuseRecommendation]) -> list[ReuseRecommendation]:
    grouped: dict[str, ReuseRecommendation] = {}
    for item in items:
        key = item.term_uri
        if key not in grouped:
            grouped[key] = item
        else:
            grouped[key].confidence = max(grouped[key].confidence, item.confidence)
            grouped[key].rationale = grouped[key].rationale if item.rationale in grouped[key].rationale else f'{grouped[key].rationale} {item.rationale}'
    return sorted(grouped.values(), key=lambda item: (item.priority, item.label))


def merge_evidence(left: list[str], right: list[str]) -> list[str]:
    merged: list[str] = []
    for item in [*left, *right]:
        if item and item not in merged:
            merged.append(item)
    return merged[:8]
