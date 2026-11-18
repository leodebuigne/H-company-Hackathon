import pytest

from orchestrator.agent_h.narration import actions_in, describe_action


@pytest.mark.parametrize(
    ("tool", "args", "said"),
    [
        ("go_to_web", {"url": "https://www.sncf-connect.com"}, "J'ouvre SNCF Connect."),
        ("click_web", {"element": 'Onglet "Trains" dans la barre'}, "J'ouvre la recherche de trains."),
        ("click_web", {"element": "Champ « Départ »"}, "J'indique la gare de départ."),
        ("click_web", {"element": "Bouton « Lancer la recherche »"}, "Je lance la recherche."),
        ("click_web", {"element": 'Button "Choisir ce tarif" for the 2de classe'}, "Je choisis le tarif."),
        ("click_web", {"element": '"Valider et payer" button in the cart summary'}, "Je valide l'achat."),
        ("write", {"text": "Nantes"}, "J'écris Nantes."),
        ("scroll_web", {"direction": "down"}, "Je parcours les résultats."),
    ],
)
def test_actions_become_short_spoken_sentences(tool, args, said):
    assert describe_action(tool, args) == said


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("write", {"text": "prenom.nom@example.com"}),  # jamais d'e-mail à l'oral
        ("write", {"text": "4970 1234 5678 9010"}),  # ni de numéro
        ("click_web", {"element": "Logo SNCF Connect"}),  # rien d'utile à dire
        ("wait_web", {"seconds": 3}),
    ],
)
def test_nothing_is_said_for_private_or_useless_actions(tool, args):
    assert describe_action(tool, args) is None


def test_actions_are_read_from_policy_events_only():
    event = {"data": {"kind": "policy_event", "tool_reqs": [{"tool_name": "scroll_web", "args": {}}]}}
    assert actions_in(event) == [("scroll_web", {})]
    assert actions_in({"data": {"kind": "tool_result"}}) == []
