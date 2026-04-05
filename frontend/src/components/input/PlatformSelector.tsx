"use client";

import React from "react";
import { Platform, PLATFORM_LABELS } from "@/lib/types";

const PLATFORMS: Platform[] = ["linkedin", "twitter", "instagram", "blog"];

interface PlatformSelectorProps {
  selected: Platform;
  onChange: (p: Platform) => void;
}

export function PlatformSelector({ selected, onChange }: PlatformSelectorProps) {
  return (
    <div className="flex flex-col gap-2">
      <span className="font-heading font-bold text-xs uppercase tracking-widest text-black">
        Platform
      </span>
      <div className="flex border-3 border-black shadow-brutal w-fit">
        {PLATFORMS.map((p, i) => (
          <button
            key={p}
            onClick={() => onChange(p)}
            className={`
              px-4 py-2.5 font-heading font-bold text-sm uppercase tracking-wide
              transition-colors duration-75 cursor-pointer
              ${i > 0 ? "border-l-3 border-black" : ""}
              ${selected === p
                ? "bg-brutal-yellow text-black"
                : "bg-white text-black hover:bg-brutal-yellow/40"
              }
            `}
          >
            {PLATFORM_LABELS[p]}
          </button>
        ))}
      </div>
    </div>
  );
}
