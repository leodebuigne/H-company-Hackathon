// Point d'entrée des contrats côté web. Importer depuis "@/lib/contracts".
export * from "./types";
export { validate, type ContractName, type ValidationResult } from "./validate";

import type { ClientAudio, ClientCancel, ClientText, WsMessage } from "./types";

/** Messages envoyés par l'interface à l'orchestrateur. */
export type ClientMessage = ClientAudio | ClientText | ClientCancel;
/** Messages envoyés par l'orchestrateur à l'interface. */
export type ServerMessage = Exclude<WsMessage, ClientMessage>;
