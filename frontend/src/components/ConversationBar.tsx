import { FormEvent, useEffect, useRef, useState } from "react";
import { MicrophoneIcon, MicrophoneSlashIcon, PaperPlaneRightIcon, PhoneDisconnectIcon } from "@phosphor-icons/react";
import { RTVIEvent, type TranscriptData } from "@pipecat-ai/client-js";
import {
  usePipecatClient,
  usePipecatClientMicControl,
  usePipecatClientTransportState,
  usePipecatConversation,
  useRTVIClientEvent,
  type ConversationMessage as PipecatConversationMessage
} from "@pipecat-ai/client-react";

import type { ConversationMessage } from "../domain/types";
import { cn } from "../utils/tailwind";
import { Button } from "./primitives/Button";
import { Divider } from "./primitives/Divider";
import { Input } from "./primitives/Input";
import { ScrollArea } from "./primitives/ScrollArea";

interface ConversationBarProps {
  className?: string;
  busy: boolean;
  messages: ConversationMessage[];
  onLocationChange?(surfaceId: string): void;
  onLocationRequest?(locationName: string): Promise<unknown> | unknown;
  onSend(text: string): Promise<void>;
}

export function ConversationBar({ className, busy, messages, onLocationChange, onLocationRequest, onSend }: ConversationBarProps) {
  const pipecatClient = usePipecatClient();
  const transportState = usePipecatClientTransportState();
  const { enableMic, isMicEnabled } = usePipecatClientMicControl();
  const { messages: pipecatMessages } = usePipecatConversation();
  const inputRef = useRef<HTMLInputElement>(null);
  const lastVoiceCommandRef = useRef<string | null>(null);
  const [draft, setDraft] = useState("");
  const [serverMessages, setServerMessages] = useState<ConversationMessage[]>([]);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [voiceConnecting, setVoiceConnecting] = useState(false);
  const [remoteMuted, setRemoteMuted] = useState(false);

  const isConnecting = voiceConnecting || ["authenticating", "authenticated", "connecting", "connected", "initializing"].includes(transportState);
  const isConnected = transportState === "ready";
  const remoteMutedActive = isConnected && remoteMuted;

  useEffect(() => {
    if (!isConnected) {
      lastVoiceCommandRef.current = null;
    }
  }, [isConnected]);

  useRTVIClientEvent(RTVIEvent.UserMuteStarted, () => {
    setRemoteMuted(true);
  });

  useRTVIClientEvent(RTVIEvent.UserMuteStopped, () => {
    setRemoteMuted(false);
  });

  useRTVIClientEvent(RTVIEvent.UserTranscript, (transcript: TranscriptData) => {
    if (!transcript.final) {
      return;
    }

    const text = transcript.text.trim();
    if (!text) {
      return;
    }

    const fingerprint = `${transcript.timestamp}:${text}`;
    if (lastVoiceCommandRef.current === fingerprint) {
      return;
    }

    lastVoiceCommandRef.current = fingerprint;
    void onSend(text);
  });

  useRTVIClientEvent(RTVIEvent.Error, (message) => {
    setVoiceError(textFromUnknown(message.data) ?? "Pipecat voice pipeline reported an error.");
  });

  useRTVIClientEvent(RTVIEvent.ServerMessage, (payload: unknown) => {
    const locationId = extractServerLocationId(payload);
    if (locationId) {
      onLocationChange?.(locationId);
    }
    const locationName = extractServerLocationName(payload);
    if (!locationId && locationName) {
      void onLocationRequest?.(locationName);
    }

    const text = extractServerMessageText(payload);
    if (!text) {
      return;
    }

    setServerMessages((current) => [
      ...current.slice(-5),
      {
        id: `pipecat-server-${Date.now()}`,
        role: "voice-agent",
        at: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
        text
      }
    ]);
  });

  const visibleMessages = [
    ...messages,
    ...serverMessages,
    ...pipecatMessages.map(mapPipecatMessage),
    ...(voiceError
      ? [
          {
            id: "pipecat-error",
            role: "system" as const,
            at: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
            text: voiceError
          }
        ]
      : [])
  ];

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text) {
      return;
    }
    setDraft("");
    if (isConnected && pipecatClient) {
      try {
        await pipecatClient.sendText(text);
      } catch (error) {
        setVoiceError(error instanceof Error ? error.message : "Pipecat text send failed.");
      }
    } else {
      await onSend(text);
    }
    inputRef.current?.focus();
  }

  async function handleVoiceClick() {
    setVoiceError(null);

    if (!pipecatClient) {
      setVoiceError("Pipecat client is not initialized.");
      return;
    }

    if (isConnected) {
      if (remoteMutedActive) {
        return;
      }
      enableMic(!isMicEnabled);
      return;
    }

    setVoiceConnecting(true);
    try {
      const response = await fetch("/api/pipecat/start", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          source: "opsec-command-deck",
          mode: "palantir-opsec-demo"
        })
      });

      const payload: unknown = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(formatPipecatStartError(payload, response.status));
      }

      setRemoteMuted(true);
      await pipecatClient.connect(payload);
      enableMic(true);
    } catch (error) {
      setVoiceError(error instanceof Error ? error.message : "Pipecat voice connection failed.");
      setRemoteMuted(false);
    } finally {
      setVoiceConnecting(false);
    }
  }

  async function handleVoiceDisconnect() {
    if (!pipecatClient) {
      return;
    }

    setVoiceError(null);
    setVoiceConnecting(false);
    setRemoteMuted(false);
    setServerMessages([]);
    lastVoiceCommandRef.current = null;

    try {
      await pipecatClient.disconnect();
    } catch (error) {
      setVoiceError(error instanceof Error ? error.message : "Pipecat disconnect failed.");
    }
  }

  return (
    <section className={cn("relative flex h-full min-w-0 flex-col gap-ui-xs border border-border bg-background/90 p-ui-xs shadow-[0_-12px_24px_rgb(0_0_0_/_0.35)]", className)}>
      <ScrollArea className="min-h-0 flex-1 mask-[linear-gradient(to_bottom,transparent_0px,black_34px)]">
        <div className="flex min-h-full flex-col justify-end gap-ui-xxs pr-ui-xs pt-8">
          {visibleMessages.slice(-4).map((message) => (
            <article className="flex items-start gap-1 text-xs" key={message.id}>
              <div
                className={[
                  "mt-2 h-px w-4 shrink-0",
                  message.role === "operator" ? "bg-fuel" : message.role === "voice-agent" ? "bg-terminal" : "bg-border",
                ].join(" ")}
              />
              <div className="min-w-0 bg-background/55 px-2 py-1 uppercase shadow-long">
                <span
                  className={[
                    "mr-1 px-1 py-px text-[10px] font-black",
                    message.role === "operator"
                      ? "bg-fuel-background text-fuel"
                      : message.role === "voice-agent"
                        ? "bg-terminal-background text-terminal"
                        : "bg-muted text-muted-foreground",
                  ].join(" ")}
                >
                  {message.role}
                </span>
                <span className="text-[11px] font-semibold text-foreground">{message.text}</span>
              </div>
            </article>
          ))}
        </div>
      </ScrollArea>

      <form className="flex items-center gap-ui-xxs" onSubmit={handleSubmit}>
        <Button
          aria-label={remoteMutedActive ? "Microphone muted by Pipecat, please wait" : isConnected ? "Toggle Pipecat microphone" : "Connect Pipecat voice"}
          className="h-9 min-w-9 px-0 @md/main:min-w-30 @md/main:px-3"
          disabled={isConnecting || remoteMutedActive}
          isLoading={isConnecting}
          loader="icon"
          onClick={handleVoiceClick}
          type="button"
          variant={
            isConnecting
              ? "micLoading"
              : remoteMutedActive
                ? "micRemoteMuted"
                : isConnected
                ? isMicEnabled
                  ? "micEnabled"
                  : "micDisabled"
                : "micRemoteMuted"
          }
        >
          {isConnecting ? null : isConnected && !isMicEnabled ? (
            <MicrophoneSlashIcon weight="bold" />
          ) : (
            <MicrophoneIcon weight="bold" />
          )}
          <span className="hidden @md/main:inline">
            {isConnecting ? "Connecting" : remoteMutedActive ? "Please wait" : isConnected ? (isMicEnabled ? "Live voice" : "Muted") : "Connect voice"}
          </span>
        </Button>
        {isConnected ? (
          <Button
            aria-label="End Pipecat voice"
            className="h-9 min-w-9 px-0"
            onClick={handleVoiceDisconnect}
            size="icon"
            type="button"
            variant="outline"
          >
            <PhoneDisconnectIcon weight="bold" />
          </Button>
        ) : null}
        <div className="relative min-w-0 flex-1">
          <Input
            ref={inputRef}
            aria-label="Enter command"
            disabled={busy}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Enter command"
            value={draft}
            className="pr-11"
          />
          <Button
            aria-label="Send command"
            className="absolute right-0 top-0 border-l-0"
            disabled={busy || !draft.trim()}
            isLoading={busy}
            loader="stripes"
            size="icon"
            type="submit"
            variant={draft.trim() ? "default" : "ghost"}
          >
            <PaperPlaneRightIcon weight="bold" />
          </Button>
        </div>
      </form>
      <Divider variant="dashed" className="h-1.5 text-foreground/30 hidden @md/main:block" />
    </section>
  );
}

function formatPipecatStartError(payload: unknown, status: number): string {
  const fallback = `Pipecat voice start failed with HTTP ${status}.`;
  if (!isRecord(payload)) {
    return fallback;
  }

  for (const key of ["text", "detail", "error", "message", "info"]) {
    const text = textFromUnknown(payload[key]);
    if (text) {
      return text;
    }
  }

  return fallback;
}

function textFromUnknown(value: unknown): string | null {
  if (typeof value === "string" && value.length > 0) {
    return value;
  }

  if (!isRecord(value)) {
    return null;
  }

  for (const key of ["text", "detail", "error", "message", "info"]) {
    const nested = textFromUnknown(value[key]);
    if (nested) {
      return nested;
    }
  }

  return null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function extractServerMessageText(payload: unknown): string | null {
  const data = extractServerMessageData(payload);
  const text = textFromUnknown(data);
  if (text) {
    return text;
  }

  if (isRecord(data)) {
    for (const key of ["type", "status", "event"]) {
      const label = typeof data[key] === "string" ? data[key] : null;
      if (label) {
        return label;
      }
    }
  }

  return null;
}

function extractServerLocationId(payload: unknown): string | null {
  const data = extractServerMessageData(payload);
  if (!isRecord(data) || data.type !== "command-deck.location") {
    return null;
  }

  const locationId = data.surfaceId ?? data.targetId;
  return typeof locationId === "string" && locationId.length > 0 ? locationId : null;
}

function extractServerLocationName(payload: unknown): string | null {
  const data = extractServerMessageData(payload);
  if (!isRecord(data) || data.type !== "command-deck.location-request") {
    return null;
  }

  const locationName = data.locationName ?? data.query ?? data.label;
  return typeof locationName === "string" && locationName.length > 0 ? locationName : null;
}

function extractServerMessageData(payload: unknown): unknown {
  return isRecord(payload) && "data" in payload ? payload.data : payload;
}

function mapPipecatMessage(message: PipecatConversationMessage, index: number): ConversationMessage {
  return {
    id: `pipecat-${message.createdAt}-${index}`,
    role:
      message.role === "user"
        ? "operator"
        : message.role === "assistant"
          ? "voice-agent"
          : "system",
    at: new Date(message.updatedAt ?? message.createdAt).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit"
    }),
    text: message.parts.map((part) => partToText(part.text)).join(" ").trim()
  };
}

function partToText(text: PipecatConversationMessage["parts"][number]["text"]): string {
  if (typeof text === "string") {
    return text;
  }

  if (typeof text === "number") {
    return String(text);
  }

  if (text && typeof text === "object" && "spoken" in text && "unspoken" in text) {
    const spoken = typeof text.spoken === "string" ? text.spoken : "";
    const unspoken = typeof text.unspoken === "string" ? text.unspoken : "";
    return `${spoken}${unspoken}`;
  }

  return "";
}
