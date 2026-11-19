/* Fichier GÉNÉRÉ par web/scripts/gen-contracts.mjs depuis contracts/schemas/. Ne pas éditer. */

// intent.schema.json
/**
 * Ce que la personne vient de dire, compris par le modèle de langage (orchestrator/ai, parse_intent). Une phrase = un Intent. Le modèle ne devine jamais : ce qui manque va dans missing[] et question propose la question à poser.
 */
export interface Intent {
  /**
   * Type de phrase. new_request : nouvelle demande d'achat. refine : préciser ou changer la recherche en cours. choose : choisir une option proposée. details : demander plus d'infos sur une option. confirm : « oui ». deny : « non ». cancel : « annule ». question : demande d'information ou de recherche sans achat (« à quelle heure ferme la pharmacie ? ») ; text porte la question. other : hors sujet ou incompris.
   */
  kind: "new_request" | "refine" | "choose" | "details" | "confirm" | "deny" | "cancel" | "question" | "other";
  /**
   * Transcription brute de la phrase.
   */
  text: string;
  /**
   * Type de demande. Sert à choisir le site et le délai de validation. boutique : un produit à acheter ; reservation : une table, un hôtel, un rendez-vous, une place de spectacle.
   */
  category: "train" | "repas" | "boutique" | "reservation" | null;
  /**
   * Ce que la personne veut, en quelques mots (« billet de train », « pizza margherita »).
   */
  object: string | null;
  /**
   * Nombre d'articles ou de voyageurs, si dit.
   */
  quantity: number | null;
  /**
   * Quand : date de départ ou de livraison. Les dates relatives (« demain ») sont résolues avec la date du jour envoyée au modèle.
   */
  when: {
    /**
     * AAAA-MM-JJ
     */
    date: string | null;
    /**
     * HH:MM, « après 14 h »
     */
    after: string | null;
    /**
     * HH:MM, « avant 20 h »
     */
    before: string | null;
    /**
     * « le plus vite possible », « dès que possible »
     */
    asap: boolean;
  };
  /**
   * Budget maximum en centimes d'euro, si dit.
   */
  budget_cents: number | null;
  /**
   * Précisions propres au type d'achat, en texte libre. Clés conseillées : train → origin, destination, class ; repas → restaurant, cuisine, size, options ; boutique → brand, size, color ; reservation → place, people, kind.
   */
  details: {
    [k: string]: string | undefined;
  };
  /**
   * Autres contraintes dites, une par entrée (« sans correspondance », « végétarien », « échangeable »).
   */
  constraints: string[];
  /**
   * Pour kind = choose ou details : rang de l'option visée, à partir de 1 (« la deuxième » → 2).
   */
  choice_index: number | null;
  /**
   * Informations indispensables qui manquent, avec un chemin de champ (« when.date », « details.origin », « category »). Vide si on peut lancer la recherche.
   */
  missing: string[];
  /**
   * Question courte à poser à l'oral pour obtenir la première information manquante. null si missing est vide.
   */
  question: string | null;
}

// option.schema.json
/**
 * Une option trouvée par l'agent H sur le site (un train, un plat, un produit). search() et refine() en renvoient 8 au maximum, dans l'ordre affiché par le site.
 */
export interface Option {
  /**
   * Identifiant stable dans la session, choisi par l'agent (ex. « opt-1 »). C'est lui qu'on passe à choose(option_id).
   */
  id: string;
  /**
   * Position dans la liste, à partir de 1. Correspond à « la première », « la deuxième ».
   */
  rank: number;
  /**
   * Nom court lisible à l'oral (« Train de 14 h 12, direct », « Pizza margherita, Bella Notte »).
   */
  title: string;
  /**
   * Prix affiché, en centimes.
   */
  price_cents: number;
  currency: "EUR";
  /**
   * Note sur 5 si le site l'affiche.
   */
  rating: number | null;
  /**
   * Une phrase de description si le site en donne une.
   */
  description: string | null;
  /**
   * Conditions affichées (échange, remboursement), telles que lues sur la page.
   */
  conditions: string | null;
  /**
   * Autres informations lues sur la page, en texte (ex. departure, arrival, duration, via, delivery_delay, restaurant).
   */
  details: {
    [k: string]: string | undefined;
  };
  /**
   * Adresse de la page de l'option si elle en a une, sinon null.
   */
  url: string | null;
}

// order-summary.schema.json
/**
 * Récapitulatif lu par l'agent H sur la page de paiement. Renvoyé par checkout() puis par recheck(). C'est ce qui est lu à l'utilisateur.
 */
export interface OrderSummary {
  /**
   * Identifiant unique de la tentative de commande (UUID v4), créé par l'agent au checkout() et conservé par recheck(). Clé d'idempotence des outils H et clé Redis approval:{order_id}.
   */
  order_id: string;
  /**
   * Nom de domaine du site (« www.sncf-connect.com », « www.ubereats.com »).
   */
  site: string;
  /**
   * Adresse de la page de paiement au moment de la lecture.
   */
  page_url: string;
  /**
   * @minItems 1
   */
  items: [
    {
      name: string;
      quantity: number;
      unit_price_cents: number | null;
      total_cents: number;
      /**
       * Options choisies, telles qu'affichées (« Grande », « Supplément fromage »).
       */
      options: string[];
    },
    ...{
      name: string;
      quantity: number;
      unit_price_cents: number | null;
      total_cents: number;
      /**
       * Options choisies, telles qu'affichées (« Grande », « Supplément fromage »).
       */
      options: string[];
    }[]
  ];
  /**
   * Frais affichés en plus des articles (livraison, service, pourboire). Vide s'il n'y en a pas.
   */
  fees: {
    label: string;
    amount_cents: number;
  }[];
  /**
   * Total à payer affiché sur la page, en centimes.
   */
  total_cents: number;
  currency: "EUR";
  /**
   * Date ou heure de départ ou de livraison, telle qu'affichée (« mercredi 18 novembre, départ 14 h 12 », « livraison vers 19 h 40 »).
   */
  when_label: string | null;
  /**
   * Mention échangeable ou remboursable si le site l'indique, sinon null.
   */
  conditions: string | null;
  /**
   * Texte exact du bouton qui engage l'argent (« Payer », « Commander et payer »).
   */
  payment_button_label: string;
  /**
   * Empreinte SHA-256 (hexadécimal) des articles, quantités et total normalisés. Algorithme dans contracts/README.md, implémentation de référence orchestrator/contracts.py:summary_hash.
   */
  hash: string;
  /**
   * Heure de lecture de la page (ISO 8601 avec fuseau).
   */
  read_at: string;
}

// site-card.schema.json
/**
 * Fiche mémoire d'un site, stockée dans Redis sous site:{domain} après une commande menée jusqu'au paiement, puis ajoutée à la consigne de l'agent à la visite suivante. Aucune donnée personnelle : ni nom, ni adresse, ni contenu de commande, ni prix.
 */
export interface SiteCard {
  domain: string;
  /**
   * Étapes du parcours, dans l'ordre, décrites de façon générique (« Fermer le bandeau cookies avec Refuser », « Cocher J'accepte les conditions de vente »).
   *
   * @maxItems 20
   */
  steps: string[];
  /**
   * Libellés de boutons utiles (« Choisir ce train », pas « Voir le détail »).
   *
   * @maxItems 20
   */
  useful_buttons: string[];
  /**
   * Pièges rencontrés et comment les éviter.
   *
   * @maxItems 20
   */
  pitfalls: string[];
  /**
   * Nombre de commandes menées sur ce site.
   */
  runs: number;
  /**
   * Commandes arrivées jusqu'à la demande d'approbation de paiement.
   */
  successful_runs: number;
  /**
   * Durée moyenne entre start() et la demande d'approbation, en secondes.
   */
  avg_duration_s: number | null;
  /**
   * Nombre moyen d'étapes de l'agent H par commande.
   */
  avg_steps: number | null;
  updated_at: string;
}

// ws-message.schema.json
/**
 * Messages échangés sur ws://localhost:8000/ws entre l'interface (web) et l'orchestrateur. Un message = un objet JSON avec un champ type. Détails et exemples dans contracts/README.md.
 */
export type WsMessage =
  | ClientAudio
  | ClientText
  | ClientConfirm
  | ClientCancel
  | ServerReady
  | ServerState
  | ServerSay
  | ServerTranscript
  | ServerIntent
  | ServerOptions
  | ServerSummary
  | ServerAgentView
  | ServerError;
export type State =
  | "listening"
  | "understanding"
  | "searching"
  | "proposing"
  | "cart"
  | "confirm_1"
  | "recheck"
  | "confirm_2"
  | "paying"
  | "done"
  | "cancelled"
  | "human_needed";

/**
 * Interface → orchestrateur. Un enregistrement complet (bouton relâché). L'orchestrateur le supprime dès la transcription.
 */
export interface ClientAudio {
  type: "audio";
  data: string;
  /**
   * ex. audio/webm;codecs=opus
   */
  mime: string;
}
/**
 * Interface → orchestrateur. Mode texte de secours : remplace un message audio.
 */
export interface ClientText {
  type: "text";
  text: string;
}
/**
 * Interface → orchestrateur. Oui ou non donné au clavier (Entrée / Échap sur la question posée), équivalent d'un « oui » ou « non » oral. Accepté seulement en proposing, confirm_1 et confirm_2.
 */
export interface ClientConfirm {
  type: "confirm";
  value: boolean;
}
/**
 * Interface → orchestrateur. Échap ou « annule ». Toujours accepté, dans n'importe quel état.
 */
export interface ClientCancel {
  type: "cancel";
}
/**
 * Orchestrateur → interface. Premier message après connexion.
 */
export interface ServerReady {
  type: "ready";
  session_id: string;
}
/**
 * Orchestrateur → interface. Changement d'état : l'interface joue le son correspondant.
 */
export interface ServerState {
  type: "state";
  state: State;
}
/**
 * Orchestrateur → interface. Phrase à dire. Si audio est null, l'interface utilise speechSynthesis en fr-FR avec text.
 */
export interface ServerSay {
  type: "say";
  text: string;
  audio: string | null;
  mime: string | null;
}
/**
 * Orchestrateur → interface. Ligne de transcription pour l'écran spectateur.
 */
export interface ServerTranscript {
  type: "transcript";
  role: "user" | "pilote";
  text: string;
}
/**
 * Orchestrateur → interface. Intent compris, pour l'écran spectateur.
 */
export interface ServerIntent {
  type: "intent";
  intent: Intent;
}
/**
 * Orchestrateur → interface. Options trouvées (8 au maximum).
 */
export interface ServerOptions {
  type: "options";
  /**
   * @maxItems 8
   */
  options: Option[];
}
/**
 * Orchestrateur → interface. Récapitulatif de la page de paiement (après checkout() et après recheck()).
 */
export interface ServerSummary {
  type: "summary";
  summary: OrderSummary;
}
/**
 * Orchestrateur → interface. Lien vers la vue en direct de l'agent H, pour l'écran spectateur.
 */
export interface ServerAgentView {
  type: "agent_view";
  agent_view_url: string;
}
/**
 * Orchestrateur → interface. Erreur. Le message est aussi dit à l'oral via un say.
 */
export interface ServerError {
  type: "error";
  code: "transcription_failed" | "not_understood" | "agent_failed" | "price_changed" | "timeout" | "internal";
  message: string;
}
