"""Phrases dites à l'utilisateur : résumé des options et confirmation de commande.

Écrites à la main plutôt que générées par un modèle : un prix ou un article inventé au moment de
la confirmation serait grave. Elles sont aussi plus rapides, et identiques dans FakeAI et HFAI.
"""

from __future__ import annotations

from orchestrator.contracts import Option, OrderSummary

MAX_SPOKEN_OPTIONS = 3


def euros(cents: int) -> str:
    """1450 -> « 14 euros 50 », 1400 -> « 14 euros »."""
    whole, rest = divmod(cents, 100)
    return f"{whole} euros" if rest == 0 else f"{whole} euros {rest:02d}"


def _rating(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def options_summary(options: list[Option]) -> str:
    """3 options au maximum : numéro, nom, prix, note. Se termine en proposant les détails."""
    if not options:
        return "Je n'ai rien trouvé. Voulez-vous que je cherche autrement ?"
    parts = []
    for number, option in enumerate(options[:MAX_SPOKEN_OPTIONS], start=1):
        note = f", noté {_rating(option.rating)} sur 5" if option.rating is not None else ""
        parts.append(f"{number}, {option.title}, {euros(option.price_cents)}{note}")
    return "J'ai trouvé : " + ". ".join(parts) + ". Voulez-vous des détails sur l'une d'elles ?"


def order_statement(summary: OrderSummary) -> str:
    """Confirmation sous forme d'affirmation, jamais de question : le oui est demandé à part."""
    articles = []
    for item in summary.items:
        label = f"{item.quantity} {item.name}"
        if item.options:
            label += " (" + ", ".join(item.options) + ")"
        articles.append(label)
    sentence = f"J'ai mis dans le panier {', '.join(articles)}, total {euros(summary.total_cents)}"
    fees = sum(fee.amount_cents for fee in summary.fees)
    if fees:
        sentence += f" dont {euros(fees)} de frais"
    if summary.when_label:
        sentence += f", {summary.when_label}"
    sentence += "."
    if summary.conditions:
        sentence += f" {summary.conditions.rstrip('.')}."
    return sentence
