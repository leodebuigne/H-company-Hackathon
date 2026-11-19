// Les phrases écrites dans l'interface (accueil, « D'accord. », messages locaux) n'ont pas d'audio du
// serveur. Sans préparation, le navigateur les disait avec sa propre voix : deux voix différentes dans
// la même conversation. Ici on demande leur audio à l'orchestrateur, une fois, et on le garde.

export type PhraseAudio = { audio: string; mime: string };

type Fetcher = (url: string, init: RequestInit) => Promise<{ ok: boolean; json(): Promise<unknown> }>;

export class PhraseVoice {
  /** Vrai quand l'orchestrateur a une voix à lui (sinon le navigateur parle seul, d'une seule voix). */
  enabled = false;
  private cache = new Map<string, PhraseAudio>();
  private pending = new Map<string, Promise<void>>();
  private generation = 0;
  private chain: Promise<void> = Promise.resolve();

  constructor(
    private base: string,
    private fetcher: Fetcher = (url, init) => fetch(url, init),
  ) {}

  get(text: string): PhraseAudio | undefined {
    return this.cache.get(text);
  }

  /** Oublie tout : la voix a changé, ou l'orchestrateur a redémarré. */
  clear() {
    this.generation += 1;
    this.cache.clear();
    this.pending.clear();
    this.chain = Promise.resolve();
  }

  /** Prépare les phrases l'une après l'autre (la voix locale n'en produit qu'une à la fois).
   *  `urgent` : sans attendre la file, pour l'accueil qui doit être prêt au premier geste. */
  prepare(texts: string[], urgent = false): Promise<void> {
    const jobs = texts.map((text) => {
      if (this.cache.has(text)) return Promise.resolve();
      const known = this.pending.get(text);
      if (known) return known;
      const generation = this.generation;
      const run = () => this.load(text, generation);
      const job = urgent ? run() : (this.chain = this.chain.then(run));
      this.pending.set(text, job);
      return job;
    });
    return Promise.all(jobs).then(() => undefined);
  }

  private async load(text: string, generation: number): Promise<void> {
    try {
      const response = await this.fetcher(`${this.base}/speak`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!response.ok) return;
      const data = (await response.json()) as { audio?: string | null; mime?: string | null };
      if (generation === this.generation && data.audio)
        this.cache.set(text, { audio: data.audio, mime: data.mime ?? "audio/wav" });
    } catch {
      // orchestrateur injoignable : la voix du navigateur dira la phrase
    } finally {
      if (generation === this.generation) this.pending.delete(text);
    }
  }
}
