import { describe, expect, it, vi } from "vitest";
import { PhraseVoice } from "./phraseVoice";

const answer = (audio: string | null) => ({
  ok: true,
  json: async () => ({ audio, mime: audio ? "audio/wav" : null }),
});

describe("PhraseVoice", () => {
  it("garde l'audio d'une phrase et ne le redemande pas", async () => {
    const fetcher = vi.fn(async (url: string) => {
      void url;
      return answer("QUJD");
    });
    const phrases = new PhraseVoice("http://localhost:8000", fetcher);
    await phrases.prepare(["D'accord."]);
    await phrases.prepare(["D'accord."]);
    expect(phrases.get("D'accord.")).toEqual({ audio: "QUJD", mime: "audio/wav" });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][0]).toBe("http://localhost:8000/speak");
  });

  it("laisse la voix du navigateur parler quand l'orchestrateur n'a pas de voix ou ne répond pas", async () => {
    const silent = new PhraseVoice("http://x", async () => answer(null));
    await silent.prepare(["Entendu."]);
    expect(silent.get("Entendu.")).toBeUndefined();

    const down = new PhraseVoice("http://x", async () => {
      throw new Error("réseau");
    });
    await down.prepare(["Entendu."]);
    expect(down.get("Entendu.")).toBeUndefined();
  });

  it("oublie les sons quand la voix change, même si une réponse arrive après", async () => {
    let release: (value: ReturnType<typeof answer>) => void = () => {};
    const fetcher = vi.fn(
      () => new Promise<ReturnType<typeof answer>>((resolve) => (release = resolve)),
    );
    const phrases = new PhraseVoice("http://x", fetcher);
    const job = phrases.prepare(["Entendu."], true);
    phrases.clear();
    release(answer("QUJD"));
    await job;
    expect(phrases.get("Entendu.")).toBeUndefined();
  });
});
