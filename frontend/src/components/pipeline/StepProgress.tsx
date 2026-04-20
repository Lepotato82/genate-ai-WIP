"use client";

import React, { useEffect, useRef } from "react";
import { AgentStep } from "./AgentStep";
import type { SSEEvent } from "@/lib/types";

interface StepProgressProps {
  events: SSEEvent[];
}

interface AgentRow {
  event: SSEEvent;
  startedAt?: number;       // wall-clock ms when start event arrived
  startElapsed?: number;    // pipeline elapsed at start
}

export function StepProgress({ events }: StepProgressProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  // Track wall-clock time each start event was received
  const startTimesRef = useRef<Record<string, number>>({});
  const startElapsedRef = useRef<Record<string, number>>({});

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  // Record wall-clock time when a start event first appears
  useEffect(() => {
    for (const ev of events) {
      const key = `${ev.agent}`;
      if (ev.status === "start" && startTimesRef.current[key] == null) {
        startTimesRef.current[key] = Date.now();
        startElapsedRef.current[key] = ev.elapsed;
      }
    }
  }, [events]);

  // Deduplicate: one row per agent, showing latest status
  const rowMap = new Map<string, AgentRow>();
  for (const ev of events) {
    const key = ev.agent;
    const existing = rowMap.get(key);
    // Prefer complete/error over start; always overwrite with later events
    if (!existing || ev.status !== "start" || existing.event.status === "start") {
      rowMap.set(key, {
        event: ev,
        startedAt: startTimesRef.current[key],
        startElapsed: startElapsedRef.current[key],
      });
    }
  }

  const rows = Array.from(rowMap.values());

  return (
    <div className="brutal-card overflow-hidden">
      <div className="bg-black text-brutal-yellow px-4 py-2.5 font-heading font-bold text-xs uppercase tracking-widest flex justify-between items-center">
        <span>Pipeline Progress</span>
        <span className="text-gray-400 normal-case font-body font-normal">
          {rows.filter(r => r.event.status === "complete").length}/{rows.length} steps
        </span>
      </div>
      <div className="max-h-96 overflow-y-auto">
        {rows.length === 0 ? (
          <p className="px-4 py-6 text-gray-400 font-body text-sm">
            Initialising pipeline…
          </p>
        ) : (
          rows.map((row, i) => {
            const durationSeconds =
              row.event.status === "complete" && row.startElapsed != null
                ? row.event.elapsed - row.startElapsed
                : undefined;
            return (
              <AgentStep
                key={i}
                event={row.event}
                startedAt={row.startedAt}
                durationSeconds={durationSeconds}
              />
            );
          })
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
