// Un enregistrement a-t-il été chevauché par la voix de Pilote ? Si oui, le micro a pu capter Pilote : le
// serveur n'acceptera alors ni « oui », ni « non », ni code, et écartera ce qui ressemble à ce que Pilote
// vient de dire (voir orchestrator/echo.py). Un appui sur le bouton ou l'espace coupe d'abord Pilote : un
// « oui » dit juste après est bien celui de la personne, il n'est donc pas marqué.
//
// Le signal passe dans le type du son (« audio/webm;codecs=opus;overlapped=1 ») : le contrat des messages
// ne change pas.

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

/** Type du son à envoyer : inchangé quand il n'y a rien à signaler. */
export function overlapMime(mime: string, tracker: OverlapTracker): string {
  return tracker.overlapped ? `${mime};overlapped=1` : mime;
}
