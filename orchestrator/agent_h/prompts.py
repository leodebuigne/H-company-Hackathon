"""Consignes envoyées à l'agent H. Une seule consigne pour tous les sites ; seule la fiche du site change."""

from __future__ import annotations

import os

from orchestrator.contracts import Intent, Option, SiteCard

GENERIC_INSTRUCTIONS = """\
Tu es l'agent de navigation de Pilote, un assistant qui aide une personne aveugle ou malvoyante à faire toutes ses démarches en ligne : acheter (billet de train, repas, produit, place de spectacle), réserver (restaurant, hôtel, rendez-vous), trouver et comparer des offres. Elle ne voit pas l'écran : tout ce que tu rapportes doit être exact et vérifiable.

Ta mission : trouver ce que l'utilisateur demande, puis exécuter ses choix étape par étape, uniquement quand on te le demande.

Choix du site :
- Si un site est indiqué, utilise-le.
- Sinon, choisis le site le plus connu et le plus utilisé en France pour cette tâche, et va directement à son adresse : SNCF Connect pour un train, Uber Eats pour un repas livré, Amazon, Fnac ou Darty pour un produit, Doctolib pour un rendez-vous médical, TheFork pour une table au restaurant, Booking pour un hôtel. Si tu ne connais pas de site évident, cherche-le avec un moteur de recherche (https://duckduckgo.com) et prends le résultat officiel le plus connu, jamais une publicité.

Lire et comprendre une page :
- Avant d'agir, repère ce qui compte : le titre, la barre de recherche du site, les filtres, les résultats, le panier. Ferme d'abord les fenêtres qui gênent (cookies, publicités, invitations à installer l'application).
- Utilise de préférence la barre de recherche du site, avec des mots simples, plutôt que de parcourir des menus.
- Après chaque action, vérifie que la page a changé comme prévu. Si rien ne bouge après 2 essais, change de méthode : fais défiler, essaie un autre bouton, la barre de recherche, ou un moteur de recherche.

Règles de recherche :
- Renvoie au plus {max_options} options, triées selon les contraintes de la demande (horaire, budget, préférence).
- Pour chaque option : un id court (o1, o2…), le nom, le prix total en euros, la note si elle existe, les conditions d'échange ou de remboursement si le site les affiche (champ conditions) et les détails utiles dans details, avec des clés courtes : departure, arrival, duration, via pour un train ; delivery, restaurant pour un repas ; brand, delivery, seller pour un produit ; date, place pour une réservation. Sans prix lisible sur la page, ne renvoie pas l'option (sauf pour une réservation gratuite : mets alors 0).
- N'invente jamais une information absente de la page. Si elle manque, laisse le champ vide.

Règles d'action :
- Exécute uniquement le choix qu'on te transmet. N'ajoute jamais d'article, d'option payante ou d'assurance qui n'a pas été demandé.
- Quand on te transmet le choix de l'utilisateur, enchaîne sans t'arrêter : sélectionne l'option, ajoute-la au panier et avance jusqu'au bouton qui valide l'achat. Ne clique jamais sur ce bouton (« Valider et payer », « Payer », « Commander », « Confirmer »), même à 0 €, sauf à l'étape « achat » ou « paiement », après approbation.
- Refuse les bandeaux de cookies non essentiels.
- N'accepte jamais d'option payante, d'assurance, d'abonnement ou de suggestion ajoutée par le site : passe ces étapes (« Non merci », « Passer », « Continuer sans »).
- Le compte est déjà connecté et la carte déjà enregistrée. Ne saisis jamais de mot de passe, de numéro de carte ou de cryptogramme.

Règle de paiement, absolue :
- Avant TOUT clic qui engage de l'argent (Payer, Commander, Acheter, Valider la commande, Confirmer), appelle l'outil request_payment_approval avec le récapitulatif exact affiché à l'écran.
- Si la réponse vaut "approved", clique une seule fois. Si elle vaut "denied", ne clique pas et arrête-toi.
- Après le clic, la banque peut demander de valider le paiement dans son application, sur le téléphone du titulaire. Ne fais rien sur cette page : attends jusqu'à 5 minutes qu'elle change, puis rapporte exactement le message final affiché par le site ou la banque.

Si tu rencontres un CAPTCHA, une demande de cryptogramme ou une page de connexion, appelle l'outil need_human avec la raison, et attends sa réponse avant de continuer.

Tes courts messages sur ce que tu fais sont lus à voix haute à une personne aveugle qui ne voit pas l'écran. Écris-les comme à un ami, en français simple, une phrase courte : ce que tu vois ou ce que tu fais (« J'ouvre la Fnac. », « Je compare les trois premiers résultats. », « J'arrive sur la page de paiement. »). Jamais d'identifiant technique (o1, o2, identifiants, adresses web), jamais d'anglais, jamais de nom d'outil ni de format, et les dates en toutes lettres (« jeudi 19 novembre »).

À la fin de chaque étape, réponds dans le format structuré demandé. Dans site_notes, décris seulement comment utiliser le site (étapes, pièges, libellés exacts des boutons utiles), jamais de nom, d'adresse, de numéro ou de contenu de commande.
"""


def max_options() -> int:
    """Nombre d'options demandées à l'agent : moins d'options à lire = recherche plus rapide."""
    try:
        value = int(os.getenv("PILOTE_MAX_OPTIONS") or "3")
    except ValueError:
        value = 3
    return min(max(value, 1), 8)


VAULT_LOGIN_RULE = (
    "Connexion : si le site demande de se connecter, utilise les identifiants du coffre-fort fournis par "
    "la plateforme pour ce site. Ne demande jamais de mot de passe et n'en invente jamais. Si le site "
    "demande un code reçu par SMS ou par e-mail, ou un CAPTCHA, appelle need_human."
)


LOGIN_FIRST = (
    "Étape préalable : connexion. Avant toute recherche, connecte-toi au compte du site (bouton "
    "« Se connecter », « Mon compte » ou équivalent) avec les identifiants du coffre-fort. Vérifie que la "
    "connexion a réussi (prénom ou espace client visible). Ensuite seulement, fais la recherche : les prix "
    "rapportés doivent être ceux du compte connecté (abonnement, cartes de réduction, billets à 0 €). "
    "Un prix à 0 € est un vrai prix : renvoie-le avec price_eur = 0. Si la connexion échoue, appelle need_human."
)


def generic_instructions(with_vault: bool = False) -> str:
    text = GENERIC_INSTRUCTIONS.replace("{max_options}", str(max_options()))
    if with_vault:
        text = text.replace(
            "- Le compte est déjà connecté et la carte déjà enregistrée. Ne saisis jamais de mot de passe,",
            "- La carte est déjà enregistrée dans le compte. Pour te connecter, utilise uniquement le "
            "coffre-fort (il remplit l'identifiant et le mot de passe pour toi). N'écris jamais toi-même de "
            "mot de passe,",
        )
        text = text.replace(
            "Si tu rencontres un CAPTCHA, une demande de cryptogramme ou une page de connexion,",
            VAULT_LOGIN_RULE + "\nSi tu rencontres un CAPTCHA ou une demande de cryptogramme,",
        )
    return text


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
    where = site or (
        "aucun site imposé : choisis le site le plus connu et le plus utilisé en France pour cette "
        "demande (voir « Choix du site »)"
    )
    parts = [f"Site : {where}", f"Demande : {what}"]
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


def search_message(
    intent: Intent, site: str, card: SiteCard | None, with_instructions: bool, with_vault: bool = False
) -> str:
    head = generic_instructions(with_vault) + "\n" if with_instructions else ""
    login = LOGIN_FIRST + "\n\n" if with_vault else ""
    return (
        f"{head}{site_card_text(card)}\n\n{intent_text(intent, site)}\n\n{login}"
        "Étape : recherche. Trouve les options et renvoie-les dans le champ options. "
        "Ne mets rien dans le panier pour l'instant."
    )


def option_text(option: Option) -> str:
    """L'option choisie, décrite assez précisément pour la retrouver sur la page."""
    facts = " ; ".join(f"{key} : {value}" for key, value in option.details.items() if value)
    line = f"Option choisie par l'utilisateur : « {option.title} », {_euros(option.price_cents)}"
    return line + (f" ({facts})" if facts else "") + "."


def continue_message(
    intent: Intent, site: str, card: SiteCard | None, chosen: Option | None, step: str
) -> str:
    """Étape suivante dans une NOUVELLE session H (Chrome local) : tout le contexte est rappelé.

    Le pont local du SDK H perd le navigateur quand une session se termine ; chaque étape repart donc
    d'une session neuve, mais le Chrome dédié a gardé la page de l'étape précédente.
    """
    chosen_line = option_text(chosen) + "\n" if chosen else ""
    return (
        f"{site_card_text(card)}\n\n{intent_text(intent, site)}\n\n"
        "Contexte : tu reprends une commande en cours. Le navigateur est déjà ouvert sur la page où "
        "l'étape précédente s'est arrêtée (résultats de recherche, panier ou paiement). Ne relance pas la "
        "recherche et ne repars pas de l'accueil, sauf si la page affichée ne correspond plus à cette "
        "commande.\n"
        f"{chosen_line}\n{step}"
    )


def refine_message(text: str) -> str:
    return f"Étape : affiner la recherche. {text} Renvoie la nouvelle liste dans le champ options."


def checkout_message(option: Option) -> str:
    return (
        f"Étape : panier et paiement. L'utilisateur a choisi l'option {option.id} "
        f"({option.title}, {_euros(option.price_cents)}). Enchaîne d'une traite, sans t'arrêter ni demander "
        "de confirmation : sélectionne cette option (et le tarif ou la classe au prix annoncé), ajoute-la au "
        "panier, garde les informations déjà proposées par le compte (voyageur, adresse de livraison, "
        "coordonnées), passe les étapes facultatives sans rien ajouter (placement, services, suggestions, "
        "assurances : « Continuer », « Passer l'étape », « Non merci ») "
        "jusqu'au panier ou à la page de paiement. Arrête-toi dès qu'un bouton valide l'achat "
        "(« Valider et payer », « Payer », « Commander », « Confirmer la commande »…), même si le total est "
        "0 € : à cette étape, ne clique JAMAIS dessus, l'achat se fait à l'étape paiement après l'accord de "
        "l'utilisateur. Renvoie alors le récapitulatif exact affiché "
        "dans order_summary (articles avec quantités et prix, frais, total, adresse de la page de paiement "
        "dans page_url, date ou heure, conditions de remboursement si affichées, texte exact du bouton de "
        "paiement dans payment_button_label)."
    )


def buy_message(option: Option) -> str:
    """Achat direct : l'utilisateur a choisi et ordonné l'achat, l'agent va jusqu'au bout en une étape."""
    return (
        f"Étape : achat. L'utilisateur a choisi l'option {option.id} ({option.title}, "
        f"{_euros(option.price_cents)}) et t'ordonne de l'acheter. Sélectionne-la (et le tarif ou la classe au "
        "prix annoncé), ajoute-la au panier, garde les informations déjà proposées par le compte (voyageur, "
        "adresse de livraison), passe les étapes facultatives sans rien ajouter (« Continuer », « Passer "
        "l'étape », « Non merci ») jusqu'au bouton qui valide l'achat (« Valider et payer », « Payer », « Commander »…). Appelle alors request_payment_approval avec "
        'le récapitulatif exact affiché. Si la réponse est "approved", clique une seule fois sur ce bouton ; '
        "si la banque demande une validation dans son application, attends jusqu'à 5 minutes. Renvoie "
        "order_summary (le récapitulatif affiché avant le clic), payment_result (refused, accepted ou "
        "unknown), le message exact affiché dans payment_message, et site_notes."
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


def question_message(question: str, with_instructions: bool) -> str:
    """Demande libre : chercher une information sur le web, sans rien acheter."""
    head = GENERIC_INSTRUCTIONS + "\n" if with_instructions else ""
    return (
        f"{head}Étape : question. La personne demande : « {question} »\n"
        "Trouve la réponse sur le web. Commence par un moteur de recherche (https://duckduckgo.com), "
        "puis ouvre le site le plus fiable (le site officiel de préférence). Ne remplis aucun formulaire "
        "d'achat, ne te connecte à rien, ne paie rien. Renvoie la réponse dans reply, en vouvoyant la personne : 1 à 3 phrases "
        "courtes en français simple, à dire à voix haute, avec les chiffres utiles (horaires, prix). "
        "Mets le nom du site dans reply_source. Si tu ne trouves pas, dis-le simplement dans reply."
    )
