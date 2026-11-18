import pytest

from orchestrator.config import Settings


def test_settings_default_to_fakes():
    s = Settings.from_env({})
    assert (s.use_fake_agent, s.use_fake_ai) == (True, True)


def test_purchase_code_must_be_three_digits():
    assert Settings.from_env({"PILOTE_PURCHASE_CODE": " 472 "}).purchase_code == "472"
    assert Settings.from_env({}).purchase_code is None
    with pytest.raises(ValueError):
        Settings.from_env({"PILOTE_PURCHASE_CODE": "12a"})
