"""Intent registry consistency and value-identity for LLM config constants."""

from astro_agent.intents import (
    PROMPT_BUILDER_NAMES,
    SUPPORTED_INTENTS,
    validate_intent_registry,
)
from astro_agent.llm import config as llm_cfg


def test_intent_registry_is_consistent():
    problems = validate_intent_registry()
    assert problems == [], problems


def test_prompt_builders_exist_for_every_intent():
    import astro_agent.llm.prompts.builder as builder

    for intent, name in PROMPT_BUILDER_NAMES.items():
        assert hasattr(builder, name), f"missing {name} for {intent}"
        assert intent in SUPPORTED_INTENTS


def test_llm_config_value_identity():
    """Extracted constants must match the previous literal values."""
    assert llm_cfg.DEFAULT_TEMPERATURE == 0.2
    assert llm_cfg.HUMANIZER_TEMPERATURE == 0.4
    assert llm_cfg.SUMMARIZE_TEMPERATURE == 0.0
    assert llm_cfg.DEFAULT_TIMEOUT_S == 120
    assert llm_cfg.DEFAULT_NUM_CTX == 16384
    assert llm_cfg.MIN_TIMEOUT_S == 15
    assert llm_cfg.MIN_NUM_CTX == 1024
    assert llm_cfg.SUMMARIZE_NUM_CTX == 4096
    assert llm_cfg.SUMMARY_MAX_WORDS == 150
    assert llm_cfg.PROMPT_PREVIEW_CHARS == 1200
    assert llm_cfg.OLLAMA_HOST.endswith("11434") or "11434" in llm_cfg.OLLAMA_HOST
    assert llm_cfg.OLLAMA_GENERATE_URL.endswith("/api/generate")
    assert llm_cfg.OLLAMA_CHAT_URL.endswith("/api/chat")
    assert llm_cfg.OLLAMA_EMBED_URL.endswith("/api/embeddings")


def test_rag_config_shares_ollama_embed_url():
    from astro_agent.rag import config as rag_cfg

    assert rag_cfg.OLLAMA_EMBED_URL == llm_cfg.OLLAMA_EMBED_URL
    assert rag_cfg.NEUTRAL_RERANK_SCORE == 0.5
    assert "bphs" in rag_cfg.BOOK_CITATION_PREFIX
    assert "manglik" in rag_cfg.DOSHA_REMEDY_ENTITY_TERMS


def test_prompts_shim_reexports_canonical_builders():
    from prompts.builder import build_prompt_for_intent as shim_build
    from astro_agent.llm.prompts.builder import build_prompt_for_intent as canon_build

    assert shim_build is canon_build
