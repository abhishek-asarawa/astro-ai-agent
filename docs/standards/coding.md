# Coding

Keep Streamlit and CLIs thin. Put consultation logic, chart math, RAG, and prompts in canonical `astro_agent` modules with typed public surfaces.

## What NOT to do

Do not bury domain orchestration in `app.py`, maintain parallel prompt trees, or sprinkle magic literals through call sites.

```bad-example
# app.py — consultation orchestration mixed into UI handlers
def on_generate_clicked():
    features = build_chart_features(...)
    intent = detect_intent(question)
    prompt = build_prompt_for_intent(intent, features, question)
    # temperature and endpoint literals at the UI layer
    for chunk, err in run_ollama_ui_query_stream(prompt):  # uses temperature=0.2 internally
        ...
    # more business rules for RAG strip, confidence, humanize...
```

```bad-example
# Root prompts/ duplicates astro_agent/llm/prompts/ — two builders drift apart
# prompts/builder.py
def build_career_prompt(features, user_question, prior_context=None):
    ...

# astro_agent/llm/prompts/builder.py  (canonical)
def build_career_prompt(features, user_question, prior_context=None):
    ...
```

```bad-example
# Bare literals at every call site
requests.get("http://localhost:11434/api/tags", timeout=(2, 3))
_call_ollama(prompt, stream=True, temperature=0.2, ...)
```

## What to do

Own a single consultation service, one prompt module, config-driven endpoints/options, and typed public APIs.

```good-example
# Preferred shape: UI calls a service; app.py only renders
# astro_agent/services/consultation.py
def run_consultation(
    birth: BirthDetails,
    question: str,
    *,
    use_agent_loop: bool = False,
) -> ConsultationResult:
    features = build_chart_features(...)
    intent = detect_intent(question)
    answer = run_agent_loop(...) if use_agent_loop else query_domain(...)
    return ConsultationResult(intent=intent, answer=answer, features=features)
```

```good-example
# Single canonical prompt module — import only from here
from astro_agent.llm.prompts.builder import build_prompt_for_intent

prompt = build_prompt_for_intent(intent, features, question, prior_context=prior)
```

```good-example
# Config-driven + typed public surface
from astro_agent.llm import config as llm_cfg

def query_ollama_once(
    prompt: str,
    *,
    temperature: float = llm_cfg.DEFAULT_TEMPERATURE,
    model_name: str | None = None,
) -> str:
    ...
```
