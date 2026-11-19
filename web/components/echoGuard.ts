// Un enregistrement a-t-il été chevauché par la voix de Pilote ? Si oui, le micro a pu capter Pilote : le
// serveur n'acceptera alors ni « oui », ni « non », ni code, et écartera ce qui ressemble à ce que Pilote
// vient de dire (voir orchestrator/echo.py). Un appui sur le bouton ou l'espace coupe d'abord Pilote : un
// « oui » dit juste après est bien celui de la personne, il n'est donc pas marqué.

export class OverlapTracker {
  private flag = false;

  /** Début d'un enregistrement : Pilote parle-t-il à cet instant ? */
  begin(pilotIsSpeaking: boolean) {
    this.flag = pilotIsSpeaking;
  }

  /** Pilote se met à parler alors que le micro est ouvert (commentaire en direct, relance…). */
  pilotStartedSpeaking() {
    this.flag = true;
  }

  get overlapped() {
    return this.flag;
  }
}

/** Champ à joindre au message audio : absent quand il n'y a rien à signaler (message inchangé). */
export function overlapField(tracker: OverlapTracker): { overlapped?: true } {
  return tracker.overlapped ? { overlapped: true } : {};
}
