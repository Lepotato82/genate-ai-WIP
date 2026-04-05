"use client";

import React, { useEffect, useRef } from "react";
import { AgentStep } from "./AgentStep";
import type { SSEEvent } from "@/lib/types";

interface StepProgressProps {
  events: SSEEvent[];
}

export function StepProgress({ events }: StepProgressProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  return (
    <div className="brutal-card overflow-hidden">
      <div className="bg-black text-brutal-yellow px-4 py-2.5 font-heading font-bold text-xs uppercase tracking-widest">
        Pipeline Progress
      </div>
      <div className="max-h-80 overflow-y-auto">
        {events.length === 0 ? (
          <p className="px-4 py-6 text-gray-400 font-body text-sm">
            Initialising pipeline...
          </p>
        ) : (
          events.map((evt, i) => <AgentStep key={i} event={evt} />)
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
