from orchestrator.config import Settings


def test_settings_default_to_fakes():
    s = Settings.from_env({})
    assert (s.use_fake_agent, s.use_fake_ai) == (True, True)


def test_there_is_no_purchase_code_any_more_and_an_old_setting_is_ignored():
    settings = Settings.from_env({"PILOTE_PURCHASE_CODE": "472"})  # ancien réglage : ignoré, sans erreur
    assert not hasattr(settings, "purchase_code")


async def test_the_demo_check_no_longer_mentions_a_secret_code(monkeypatch):
    from orchestrator.check import OK, check_settings

    monkeypatch.setenv("USE_FAKE_AGENT", "0")
    monkeypatch.setenv("USE_FAKE_AI", "0")
    monkeypatch.setenv("PILOTE_DIRECT_BUY", "1")
    status, text = await check_settings()
    assert status == OK and "achat direct" in text and "« oui » demandé avant de payer" in text
    assert "code secret" not in text
