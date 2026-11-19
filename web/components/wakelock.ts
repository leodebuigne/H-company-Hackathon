// Garde l'écran allumé pendant une session (Wake Lock API). Repli silencieux si l'API manque
// ou si le navigateur refuse : l'application marche pareil, l'écran peut seulement se verrouiller.
// Le navigateur relâche le verrou quand la page passe en arrière-plan : on le redemande au retour.

interface SentinelLike {
  release(): Promise<void>;
  addEventListener?(type: "release", listener: () => void): void;
}
interface NavigatorLike {
  wakeLock?: { request(type: "screen"): Promise<SentinelLike> };
}
interface DocumentLike {
  visibilityState: string;
  addEventListener(type: "visibilitychange", listener: () => void): void;
  removeEventListener(type: "visibilitychange", listener: () => void): void;
}

export class WakeLockKeeper {
  private sentinel: SentinelLike | null = null;
  private wanted = false;
  private readonly onVisibility = () => {
    if (this.wanted && this.doc?.visibilityState === "visible") void this.request();
  };

  constructor(
    private nav: NavigatorLike | undefined = typeof navigator !== "undefined" ? navigator : undefined,
    private doc: DocumentLike | undefined = typeof document !== "undefined" ? document : undefined
  ) {}

  get supported() {
    return !!this.nav?.wakeLock;
  }

  get held() {
    return this.sentinel !== null;
  }

  async acquire() {
    if (this.wanted) return;
    this.wanted = true;
    this.doc?.addEventListener("visibilitychange", this.onVisibility);
    await this.request();
  }

  async release() {
    this.wanted = false;
    this.doc?.removeEventListener("visibilitychange", this.onVisibility);
    const sentinel = this.sentinel;
    this.sentinel = null;
    try {
      await sentinel?.release();
    } catch {
      // déjà relâché
    }
  }

  private async request() {
    if (!this.nav?.wakeLock || this.sentinel) return;
    try {
      const sentinel = await this.nav.wakeLock.request("screen");
      if (!this.wanted) return void sentinel.release().catch(() => {});
      this.sentinel = sentinel;
      sentinel.addEventListener?.("release", () => {
        if (this.sentinel === sentinel) this.sentinel = null;
      });
    } catch {
      // refusé (économie d'énergie, page pas visible) : on continue sans
    }
  }
}
