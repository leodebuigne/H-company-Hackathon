from types import SimpleNamespace

from orchestrator.ai import conversation
from orchestrator.ai.conversation import facts_ok


def test_invented_price_or_time_is_refused():
    facts = "Option 1 : TGV 14 heures 44, 49 euros."
    assert facts_ok("Le premier train part à 14 h 44 pour 49 euros. Il vous plaît ?", facts, facts)
    assert not facts_ok("Le premier train coûte 39 euros.", facts, facts)
    assert not facts_ok("Il part à 15 heures.", facts, facts)


def test_claiming_a_purchase_is_refused_when_the_reference_does_not():
    ref = "Dites-moi ce que vous voulez commander."
    assert not facts_ok("C'est acheté, votre billet est payé !", ref, ref)
    assert facts_ok("Avec plaisir ! Que puis-je faire pour vous ?", ref, ref)


class _Chat:
    def __init__(self, text=None, error=None):
        async def create(**kwargs):
            if error:
                raise error
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


async def test_reply_uses_the_model_when_facts_hold():
    said = await conversation.reply(
        _Chat("Avec plaisir ! Voulez-vous un train ou un repas ?"),
        "m",
        situation="s",
        fallback="Dites-moi ce que vous voulez commander.",
        heard="merci beaucoup",
    )
    assert said.startswith("Avec plaisir")


async def test_reply_falls_back_on_error_or_invented_fact():
    ref = "Le train coûte 49 euros."
    assert await conversation.reply(_Chat(error=TimeoutError()), "m", situation="s", fallback=ref) == ref
    assert (
        await conversation.reply(_Chat("Il coûte 12 euros."), "m", situation="s", fallback=ref, facts=ref)
        == ref
    )


def test_numbers_written_in_words_are_refused():
    facts = "Numéro 1 : départ 14:44, 49 euros."
    assert not facts_ok("Il part à quatorze heures quarante-quatre.", facts, facts)
