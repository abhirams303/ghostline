"use client";

import { useEffect, useState } from "react";

import type { PipecatClient } from "@pipecat-ai/client-js";
import { PipecatClientAudio, PipecatClientProvider } from "@pipecat-ai/client-react";

import { CommandDeck } from "@/CommandDeck";

export function CommandDeckShell() {
  const [pipecatClient, setPipecatClient] = useState<PipecatClient | null>(null);

  useEffect(() => {
    let mounted = true;
    let nextClient: PipecatClient | null = null;

    async function createClient() {
      const [{ PipecatClient }, { DailyTransport }] = await Promise.all([
        import("@pipecat-ai/client-js"),
        import("@pipecat-ai/daily-transport"),
      ]);

      if (!mounted) {
        return;
      }

      nextClient = new PipecatClient({
        transport: new DailyTransport({ bufferLocalAudioUntilBotReady: true }),
        enableCam: false,
        enableMic: false,
      });
      setPipecatClient(nextClient);
    }

    void createClient();

    return () => {
      mounted = false;
      void nextClient?.disconnect();
    };
  }, []);

  if (!pipecatClient) {
    return (
      <main className="grid h-svh place-items-center bg-black font-mono text-xs uppercase text-terminal">
        Initializing command deck
      </main>
    );
  }

  return (
    <PipecatClientProvider client={pipecatClient}>
      <PipecatClientAudio />
      <CommandDeck />
    </PipecatClientProvider>
  );
}
