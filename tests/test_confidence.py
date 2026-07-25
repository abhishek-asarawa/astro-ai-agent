from astro_agent.utils.confidence import calibrate_confidence


def test_calibrate_confidence_defaults_when_missing():
    assert calibrate_confidence(None, ["a", "b"], ["ref1"]) == 50


def test_calibrate_confidence_caps_without_refs():
    assert calibrate_confidence(85, ["a", "b", "c"], []) == 55


def test_calibrate_confidence_caps_with_few_evidence():
    assert calibrate_confidence(80, ["only one"], ["ref1"]) == 50


def test_calibrate_confidence_keeps_high_when_grounded():
    assert calibrate_confidence(85, ["a", "b"], ["ref1", "ref2"]) == 85


def test_calibrate_confidence_clamps_bounds():
    assert calibrate_confidence(150, ["a", "b"], ["ref1"]) == 100
    assert calibrate_confidence(-10, ["a", "b"], ["ref1"]) == 0
