import { NextResponse } from "next/server";

const DEFAULT_PIPECAT_CLOUD_API_BASE = "https://api.pipecat.daily.co/v1/public";

export async function POST(request: Request) {
  const apiKey = process.env.PIPECAT_CLOUD_API_KEY;
  const agentName = process.env.PIPECAT_AGENT_NAME ?? "gradient-bang-bot";
  const apiBase = process.env.PIPECAT_CLOUD_API_BASE ?? DEFAULT_PIPECAT_CLOUD_API_BASE;

  if (!apiKey) {
    return NextResponse.json(
      {
        error: "PIPECAT_CLOUD_API_KEY is not configured for this Next.js server.",
      },
      { status: 503 }
    );
  }

  const body = await request.json().catch(() => ({}));
  const upstreamResponse = await fetch(`${apiBase.replace(/\/$/, "")}/${agentName}/start`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      createDailyRoom: true,
      body,
    }),
  });

  const payload = await upstreamResponse.json().catch(() => ({
    error: `Pipecat Cloud returned HTTP ${upstreamResponse.status}.`,
  }));

  return NextResponse.json(payload, { status: upstreamResponse.status });
}
