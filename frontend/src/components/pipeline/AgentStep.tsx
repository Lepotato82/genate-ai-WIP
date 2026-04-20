"use client";

import React, { useEffect, useState } from "react";
import { Badge, statusToBadgeVariant } from "@/components/ui/Badge";
import { formatAgentName } from "@/lib/api";
import type { SSEEvent } from "@/lib/types";

interface AgentStepProps {
  event: SSEEvent;
  /** Wall-clock time (ms) when this step's start event was received */
  startedAt?: number;
  /** Elapsed seconds for completed steps (complete.elapsed - start.elapsed) */
  durationSeconds?: number;
}

export function AgentStep({ event, startedAt, durationSeconds }: AgentStepProps) {
  const badgeVariant = statusToBadgeVariant(event.status);
  const isRunning = event.status === "start";

  // Live ticking counter for in-progress steps
  const [runningFor, setRunningFor] = useState(0);
  useEffect(() => {
    if (!isRunning || startedAt == null) return;
    const tick = () => setRunningFor(Math.floor((Date.now() - startedAt) / 1000));
    tick();
    const id = setInterval(tick, 500);
    return () => clearInterval(id);
  }, [isRunning, startedAt]);

  const timeDisplay = isRunning
    ? `${runningFor}s…`
    : durationSeconds != null
    ? `${durationSeconds.toFixed(1)}s`
    : `${event.elapsed.toFixed(1)}s`;

  return (
    <div
      className={`flex items-center gap-3 py-2.5 px-4 border-b border-black last:border-b-0 ${
        isRunning ? "bg-yellow-50" : ""
      }`}
    >
      <span className="font-heading font-bold text-xs text-gray-400 w-6 shrink-0 tabular-nums">
        {String(event.step).padStart(2, "0")}
      </span>
      <span className="font-heading font-bold text-sm flex-1 uppercase tracking-wide">
        {formatAgentName(event.agent)}
      </span>
      <Badge label={isRunning ? "running" : event.status} variant={badgeVariant} />
      <span
        className={`font-body text-xs tabular-nums w-12 text-right shrink-0 ${
          isRunning ? "text-orange-500 font-bold" : "text-gray-400"
        }`}
      >
        {timeDisplay}
      </span>
    </div>
  );
}
