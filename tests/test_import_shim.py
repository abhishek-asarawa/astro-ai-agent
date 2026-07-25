"""Ensure the astro_agent package exposes key public symbols from all sub-packages."""

import importlib

PUBLIC_SYMBOLS = {
    "astro_agent.chart.engine": ["build_chart_features", "generate_full_chart"],
    "astro_agent.chart.dashas": ["calculate_dashas", "calculate_antardashas"],
    "astro_agent.chart.lords": ["RASHIS", "get_house_lords"],
    "astro_agent.llm.client": ["query_ollama_once", "resolve_ollama_config"],
    "astro_agent.llm.prompts.builder": ["build_prompt_for_intent"],
    "astro_agent.llm.config": ["DEFAULT_TEMPERATURE", "OLLAMA_HOST"],
    "astro_agent.intents": ["SUPPORTED_INTENTS", "validate_intent_registry"],
    "astro_agent.service.consultation": ["run_consultation", "ConsultationRequest"],
    "astro_agent.rag.config": [],
    "astro_agent.rag.inject": ["build_rag_enriched_prompt", "_strip_unknown_refs"],
    "astro_agent.routing.intent_router": ["detect_intent", "SUPPORTED_INTENTS"],
    "astro_agent.utils.cities": ["CITY_COORDINATES", "resolve_city_coordinates"],
    "astro_agent.utils.text_utils": ["strip_reasoning_blocks", "extract_ref_ids"],
    "astro_agent.utils.tracer": ["trace_interaction", "trace_llm_call"],
}


def test_all_public_symbols_importable():
    for module_path, symbols in PUBLIC_SYMBOLS.items():
        mod = importlib.import_module(module_path)
        for name in symbols:
            assert hasattr(mod, name), f"{module_path} is missing export: {name}"
