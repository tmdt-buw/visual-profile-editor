import base64
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / 'requirement-reuse-service'
sys.path.insert(0, str(SERVICE_ROOT))

from requirement_reuse_service.models import AnalysisRequest, ConstraintGenerationRequest, RecommendationRequest
from requirement_reuse_service.service import analyze_payload, generate_constraints, recommend_reuse


def test_text_analysis_recommends_reuse_terms():
    analysis = analyze_payload(
        AnalysisRequest(
            text='Datasets need title, description, lifecycle phase, license, format, and semantic anchors to AAS submodels.'
        )
    )

    assert {item.category for item in analysis.requirements} >= {'Dataset Metadata', 'Semantic Anchors'}

    recommendations = recommend_reuse(RecommendationRequest(analysis=analysis)).recommendations
    uris = {item.term_uri for item in recommendations}

    assert 'http://purl.org/dc/terms/title' in uris
    assert 'https://w3id.org/cx#semanticAnchor' in uris
    assert any(item.priority == 1 for item in recommendations)


def test_aas_json_extracts_semantic_ids_and_generates_shacl():
    analysis = analyze_payload(
        AnalysisRequest(
            artifacts=[
                {
                    'name': 'pump-submodel.json',
                    'content': '{"submodels":[{"idShort":"PumpStatus","semanticId":{"keys":[{"value":"https://example.org/aas/PumpStatus"}]}}]}',
                }
            ]
        )
    )

    assert any(candidate.kind.startswith('aas-') for candidate in analysis.semantic_candidates)
    assert any(attribute.label == 'idShort' and attribute.value == 'PumpStatus' for attribute in analysis.extracted_attributes)

    recommendations = recommend_reuse(RecommendationRequest(analysis=analysis)).recommendations
    generated = generate_constraints(
        ConstraintGenerationRequest(
            analysis=analysis,
            recommendations=recommendations,
            selected_recommendation_ids=[item.id for item in recommendations],
        )
    )

    assert 'sh:NodeShape' in generated.shacl
    assert 'GeneratedConstructionDatasetProfile' in generated.profile_draft['classes']



def test_aasx_package_extracts_embedded_aas_json():
    package = io.BytesIO()
    aas_payload = {
        'submodels': [
            {
                'idShort': 'PumpMaintenance',
                'semanticId': {'keys': [{'value': 'https://example.org/aas/PumpMaintenance'}]},
            }
        ]
    }
    with zipfile.ZipFile(package, 'w') as archive:
        archive.writestr('aas/submodel.json', json.dumps(aas_payload))

    analysis = analyze_payload(
        AnalysisRequest(
            artifacts=[
                {
                    'name': 'pump.aasx',
                    'content': base64.b64encode(package.getvalue()).decode('ascii'),
                    'content_encoding': 'base64',
                }
            ]
        )
    )

    assert any(summary.kind == 'aasx' for summary in analysis.artifacts)
    assert any(candidate.label == 'PumpMaintenance' for candidate in analysis.semantic_candidates)
    assert any(attribute.label == 'idShort' and attribute.value == 'PumpMaintenance' for attribute in analysis.extracted_attributes)
    assert any(candidate.property == 'hasAASSubmodel' for candidate in analysis.metadata_candidates)
