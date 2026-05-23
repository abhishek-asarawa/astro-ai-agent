"""Pydantic schema for structured domain LLM responses."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DomainResponseSchema(BaseModel):
    summary: str
    evidence: list[str] = Field(default_factory=list)
    risk: str
    opportunity: str
    confidence: int = Field(ge=0, le=100)


def domain_response_json_schema() -> dict:
    return DomainResponseSchema.model_json_schema()
