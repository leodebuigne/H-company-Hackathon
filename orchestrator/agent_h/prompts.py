"""Consignes envoyées à l'agent H. Une seule consigne pour tous les sites ; seule la fiche du site change."""

from __future__ import annotations

from orchestrator.contracts import Intent, Option, SiteCard

GENERIC_INSTRUCTIONS = """\
Tu es l'agent de navigation de Pilote, un assistant qui fait des achats en ligne pour une personne aveugle. Elle ne voit pas l'écran : tout ce que tu rapportes doit être exact et vérifiable.

Ta mission : trouver ce que l'utilisateur demande sur le site indiqué, puis exécuter ses choix étape par étape, uniquement quand on te le demande.

Règles de recherche :
- Renvoie au plus 8 options, triées selon les contraintes de la demande (horaire, budget, préférence).
- Pour chaque option : un id court (o1, o2…), le nom, le prix total en euros, la note si elle existe, les conditions d'échange ou de remboursement si le site les affiche (champ conditions) et les détails utiles dans details : departure, arrival, duration, via pour un train ; delivery, restaurant pour un repas. Sans prix lisible sur la page, ne renvoie pas l'option.
- N'invente jamais une information absente de la page. Si elle manque, laisse le champ vide.

Règles d'action :
- Exécute uniquement le choix qu'on te transmet. N'ajoute jamais d'article, d'option payante ou d'assurance qui n'a pas été demandé.
- Refuse les bandeaux de cookies non essentiels.
- Le compte est déjà connecté et la carte déjà enregistrée. Ne saisis jamais de mot de passe, de numéro de carte ou de cryptogramme.

Règle de paiement, absolue :
- Avant TOUT clic qui engage de l'argent (Payer, Commander, Acheter, Valider la commande, Confirmer), appelle l'outil request_payment_approval avec le récapitulatif exact affiché à l'écran.
- Si la réponse vaut "approved", clique une seule fois. Si elle vaut "denied", ne clique pas et arrête-toi.
- Après le clic, la banque peut demander de valider le paiement dans son application, sur le téléphone du titulaire. Ne fais rien sur cette page : attends jusqu'à 5 minutes qu'elle change, puis rapporte exactement le message final affiché par le site ou la banque.

Si tu rencontres un CAPTCHA, une demande de cryptogramme ou une page de connexion, appelle l'outil need_human avec la raison, et attends sa réponse avant de continuer.

À la fin de chaque étape, réponds dans le format structuré demandé. Dans site_notes, décris seulement comment utiliser le site (étapes, pièges, libellés exacts des boutons utiles), jamais de nom, d'adresse, de numéro ou de contenu de commande.
"""


def site_card_text(card: SiteCard | None) -> str:
    if card is None or (not card.steps and not card.pitfalls):
        return "Fiche du site : aucune (première visite)."
    lines = [f"Fiche du site {card.domain} ({card.runs} visites précédentes) :"]
    lines += [f"- Étape connue : {s}" for s in card.steps]
    lines += [f"- Bouton utile : {b}" for b in card.useful_buttons]
    lines += [f"- Piège connu : {p}" for p in card.pitfalls]
    return "\n".join(lines)


def _euros(cents: int) -> str:
    return f"{cents / 100:.2f}".replace(".", ",") + " €"


def intent_text(intent: Intent, site: str) -> str:
    """La demande de l'utilisateur, telle que le contrat Intent la décrit."""
    what = " ".join(part for part in (intent.category, intent.object) if part) or "achat"
    if intent.quantity and intent.quantity > 1:
        what += f" (quantité : {intent.quantity})"
    parts = [f"Site : {site}", f"Demande : {what}"]
    parts += [f"{key} : {value}" for key, value in intent.details.items()]
    when = intent.when
    if when.date:
        parts.append(f"Date : {when.date.isoformat()}")
    if when.after:
        parts.append(f"Heure : à partir de {when.after}")
    if when.before:
        parts.append(f"Heure : avant {when.before}")
    if when.asap:
        parts.append("Le plus vite possible")
    if intent.budget_cents is not None:
        parts.append(f"Budget maximum : {_euros(intent.budget_cents)}")
    if intent.constraints:
        parts.append("Contraintes : " + " ; ".join(intent.constraints))
    return "\n".join(parts)


def search_message(intent: Intent, site: str, card: SiteCard | None, with_instructions: bool) -> str:
    head = GENERIC_INSTRUCTIONS + "\n" if with_instructions else ""
    return (
        f"{head}{site_card_text(card)}\n\n{intent_text(intent, site)}\n\n"
        "Étape : recherche. Trouve les options et renvoie-les dans le champ options. "
        "Ne mets rien dans le panier pour l'instant."
    )


def refine_message(text: str) -> str:
    return f"Étape : affiner la recherche. {text} Renvoie la nouvelle liste dans le champ options."


def checkout_message(option: Option) -> str:
    return (
        f"Étape : panier. Choisis l'option {option.id} ({option.title}). Mets-la dans le panier et va "
        "jusqu'à la page de paiement, sans cliquer sur le bouton final. Renvoie le récapitulatif exact "
        "affiché dans order_summary (articles avec quantités et prix, frais, total, adresse de la page "
        "de paiement dans page_url, date ou heure de livraison, conditions de remboursement si "
        "affichées, texte exact du bouton de paiement dans payment_button_label)."
    )


def recheck_message() -> str:
    return (
        "Étape : relecture. Relis la page de paiement actuelle sans rien cliquer et renvoie le "
        "récapitulatif exact affiché dans order_summary, avec page_url et payment_button_label."
    )


def pay_message() -> str:
    return (
        "Étape : paiement. Appelle request_payment_approval avec le récapitulatif affiché. Si la réponse "
        'est "approved", clique une seule fois sur le bouton de paiement. Si la banque demande une '
        "validation dans son application, attends jusqu'à 5 minutes que le titulaire valide sur son "
        "téléphone. Renvoie ensuite payment_result (refused, accepted ou unknown), le message exact "
        "affiché dans payment_message, et site_notes."
    )
