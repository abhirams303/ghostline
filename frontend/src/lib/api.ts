import type { AnalyzeRequest, AnalyzeResponse } from "@/types/findings";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000";


export async function analyzeTarget(payload: AnalyzeRequest): Promise<AnalyzeResponse> {
  const response = await fetch(`${API_BASE_URL}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    throw new Error(`Analyze request failed with status ${response.status}`);
  }

  return (await response.json()) as AnalyzeResponse;
}


export function streamThreatBrief(runId: string, onChunk: (chunk: string) => void): () => void {
  const source = new EventSource(`${API_BASE_URL}/stream/${runId}`);
  source.onmessage = (event) => onChunk(event.data);
  source.onerror = () => source.close();
  return () => source.close();
}
