// Où se connecter, et avec quel jeton. Le build fige l'adresse par défaut (NEXT_PUBLIC_ORCHESTRATOR_WS_URL) ;
// un téléphone, lui, ouvre un lien d'appairage : « https://…vercel.app/#server=wss%3A%2F%2F…&token=… ».
// Tout ce qui suit le # reste dans le navigateur : ni Vercel ni le tunnel ne le voient, et il ne finit pas
// dans leurs journaux. L'adresse et le jeton sont gardés dans le navigateur, puis le # est effacé de la barre.

export type ServerConfig = { wsUrl: string; httpUrl: string; token: string | null };
export type Pairing = { wsUrl: string; token: string };
export type KeyValueStore = Pick<Storage, "getItem" | "setItem" | "removeItem">;

const STORAGE_KEY = "pilote-server";
const TOKEN_PATTERN = /^[A-Za-z0-9_-]{16,128}$/;
export const DEFAULT_WS_URL = process.env.NEXT_PUBLIC_ORCHESTRATOR_WS_URL ?? "ws://localhost:8000/ws";

/** `wss://` partout ; `ws://` seulement sur cette machine (sinon le jeton circulerait en clair). */
export function isAllowedWsUrl(value: string): boolean {
  try {
    const url = new URL(value);
    if (url.username || url.password || url.hash) return false;
    if (url.protocol === "wss:") return true;
    return url.protocol === "ws:" && ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  } catch {
    return false;
  }
}

export const isValidToken = (value: unknown): value is string =>
  typeof value === "string" && TOKEN_PATTERN.test(value);

/** `ws://hôte/ws` -> `http://hôte` (pour `/voice` et `/health`). */
export function httpUrlFor(wsUrl: string): string {
  return wsUrl.replace(/^ws/, "http").replace(/\/ws\/?$/, "");
}

/** Lit « #server=…&token=… ». Renvoie null si ce n'est pas un lien d'appairage valide. */
export function parsePairingHash(hash: string): Pairing | null {
  const params = new URLSearchParams(hash.replace(/^#/, ""));
  const wsUrl = params.get("server");
  const token = params.get("token");
  if (!wsUrl || !isAllowedWsUrl(wsUrl) || !isValidToken(token)) return null;
  return { wsUrl, token };
}

export function loadServerConfig(storage: KeyValueStore | null, defaultWsUrl: string = DEFAULT_WS_URL): ServerConfig {
  const fallback = { wsUrl: defaultWsUrl, httpUrl: httpUrlFor(defaultWsUrl), token: null };
  try {
    const raw = storage?.getItem(STORAGE_KEY);
    if (!raw) return fallback;
    const stored = JSON.parse(raw) as Partial<Pairing>;
    if (!stored.wsUrl || !isAllowedWsUrl(stored.wsUrl) || !isValidToken(stored.token)) return fallback;
    return { wsUrl: stored.wsUrl, httpUrl: httpUrlFor(stored.wsUrl), token: stored.token };
  } catch {
    return fallback;
  }
}

export function savePairing(storage: KeyValueStore | null, pairing: Pairing): boolean {
  try {
    storage?.setItem(STORAGE_KEY, JSON.stringify(pairing));
    return storage !== null;
  } catch {
    return false; // navigation privée : l'appairage ne durerait pas, on le dit à la personne
  }
}

export function forgetPairing(storage: KeyValueStore | null) {
  try {
    storage?.removeItem(STORAGE_KEY);
  } catch {
    // rien à oublier
  }
}

/** Sous-protocoles du WebSocket : le jeton y passe (l'adresse, elle, finirait dans les journaux du tunnel). */
export const wsProtocols = (token: string | null): string[] | undefined =>
  token ? ["pilote", `token.${token}`] : undefined;

export const authHeaders = (token: string | null): Record<string, string> =>
  token ? { Authorization: `Bearer ${token}` } : {};

type LocationLike = { hash: string; pathname: string; search: string };
type HistoryLike = { replaceState: (data: unknown, unused: string, url: string) => void };

/** Retire le lien d'appairage de la barre d'adresse (même s'il est invalide) et le renvoie. */
export function takePairingFromLocation(location: LocationLike, history: HistoryLike): Pairing | null {
  if (!/(^|[#&])(server|token)=/.test(location.hash)) return null;
  const pairing = parsePairingHash(location.hash);
  history.replaceState(null, "", `${location.pathname}${location.search}`);
  return pairing;
}

export function browserStorage(): KeyValueStore | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

/** Adresse et jeton à utiliser maintenant (le navigateur d'abord, sinon l'adresse du build). */
export const getServerConfig = (): ServerConfig => loadServerConfig(browserStorage());
