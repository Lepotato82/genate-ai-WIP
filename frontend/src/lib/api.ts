import type {
  GenerateRequest,
  GenerateResult,
  Platform,
  SSEEvent,
} from "./types";

/**
 * Stream content generation via POST SSE.
 *
 * Uses fetch + ReadableStream rather than EventSource because the endpoint is
 * a POST (EventSource only supports GET).
 *
 * SSE frame format: `data: {...}\n\n`
 * The final event (agent="pipeline", status="complete") carries:
 *   run_id, passes, formatted_content, evaluator_output
 */
export async function streamGenerate(
  req: GenerateRequest,
  onEvent: (event: SSEEvent) => void,
  onComplete: (result: GenerateResult) => void,
  onError: (error: Error) => void,
): Promise<void> {
  let response: Response;

  try {
    response = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
  } catch (err) {
    onError(new Error(`Network error: ${String(err)}`));
    return;
  }

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    onError(new Error(`API error ${response.status}: ${text}`));
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    onError(new Error("No response body"));
    return;
  }

  const decoder = new TextDecoder();
  let carry = ""; // buffer for incomplete SSE frames

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      carry += decoder.decode(value, { stream: true });

      // Split on double-newline (SSE frame boundary)
      const frames = carry.split("\n\n");
      // Last element may be an incomplete frame — keep it in carry
      carry = frames.pop() ?? "";

      for (const frame of frames) {
        const line = frame.trim();
        if (!line.startsWith("data:")) continue;

        const jsonStr = line.slice("data:".length).trim();
        if (!jsonStr) continue;

        let event: SSEEvent;
        try {
          event = JSON.parse(jsonStr) as SSEEvent;
        } catch {
          continue; // skip malformed frames
        }

        onEvent(event);

        if (event.agent === "pipeline" && event.status === "complete") {
          if (
            event.run_id &&
            event.formatted_content &&
            event.evaluator_output
          ) {
            const result: GenerateResult = {
              run_id: event.run_id,
              platform: req.platform,
              content_type: req.content_type ?? "auto",
              formatted_content: event.formatted_content,
              evaluator_output: event.evaluator_output,
              passes: event.passes ?? false,
            };
            onComplete(result);
          }
        }
      }
    }
  } catch (err) {
    onError(new Error(`Stream read error: ${String(err)}`));
  } finally {
    reader.releaseLock();
  }
}

/** Human-readable agent name from snake_case identifier. */
export function formatAgentName(agent: string): string {
  return agent
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

/** Derive the active platform from the latest SSE events. */
export function getResultPlatform(events: SSEEvent[]): Platform {
  // The platform is known from the request, not the events — pass it in as req.platform
  // This helper is for display use only
  const final = [...events].reverse().find((e) => e.run_id);
  return ((final?.formatted_content as { platform?: Platform } | undefined)
    ?.platform ?? "linkedin") as Platform;
}
