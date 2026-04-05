import React from "react";
import { Badge, statusToBadgeVariant } from "@/components/ui/Badge";
import { formatAgentName } from "@/lib/api";
import type { SSEEvent } from "@/lib/types";

interface AgentStepProps {
  event: SSEEvent;
}

export function AgentStep({ event }: AgentStepProps) {
  const badgeVariant = statusToBadgeVariant(event.status);

  return (
    <div className="flex items-center gap-3 py-2.5 px-4 border-b border-black last:border-b-0">
      <span className="font-heading font-bold text-xs text-gray-400 w-6 shrink-0 tabular-nums">
        {String(event.step).padStart(2, "0")}
      </span>
      <span className="font-heading font-bold text-sm flex-1 uppercase tracking-wide">
        {formatAgentName(event.agent)}
      </span>
      <Badge label={event.status} variant={badgeVariant} />
      <span className="font-body text-xs text-gray-400 tabular-nums w-12 text-right shrink-0">
        {event.elapsed.toFixed(1)}s
      </span>
    </div>
  );
}
