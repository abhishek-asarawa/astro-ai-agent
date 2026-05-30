from astro_agent.utils.text_utils import format_consumer_text, soften_jargon, strip_ref_tags


def test_strip_ref_tags():
    assert strip_ref_tags("Hello [ref:bphs-1] world") == "Hello world"


def test_soften_jargon_debilitated():
    assert "weakened" in soften_jargon("Mercury is debilitated").lower()


def test_format_consumer_text_strips_refs_and_jargon():
    text = "The native has a debilitated 5th lord [ref:x]."
    out = format_consumer_text(text)
    assert "[ref:" not in out
    assert "native" not in out.lower() or "you" in out.lower()


def test_format_consumer_text_empty():
    assert format_consumer_text("") == ""
