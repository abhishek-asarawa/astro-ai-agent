import json

import pytest
from pydantic import ValidationError

from astro_agent.llm.prompts.schema import DomainResponseSchema, domain_response_json_schema


def test_schema_json_serializable():
    schema = domain_response_json_schema()
    json.dumps(schema)
    assert "properties" in schema


def test_validates_good_payload():
    obj = DomainResponseSchema(
        summary="Stable period.",
        evidence=["Saturn in 10th supports discipline"],
        risk="Delays possible",
        opportunity="Growth after effort",
        confidence=72,
    )
    assert obj.confidence == 72


def test_rejects_bad_confidence():
    with pytest.raises(ValidationError):
        DomainResponseSchema(
            summary="x",
            evidence=[],
            risk="x",
            opportunity="x",
            confidence=150,
        )
