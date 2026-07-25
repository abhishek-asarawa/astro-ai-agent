"""Deprecated shim — use ``astro_agent.llm.prompts`` instead."""

from astro_agent.llm.prompts.builder import (  # noqa: F401
    build_career_prompt,
    build_family_prompt,
    build_general_prompt,
    build_health_prompt,
    build_prompt_for_intent,
    build_wealth_prompt,
)
from astro_agent.llm.prompts.schema import DomainResponseSchema, domain_response_json_schema  # noqa: F401
