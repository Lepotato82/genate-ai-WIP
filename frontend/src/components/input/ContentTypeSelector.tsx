"use client";

import React from "react";
import { Platform, PLATFORM_CONTENT_TYPES, CONTENT_TYPE_LABELS } from "@/lib/types";

interface ContentTypeSelectorProps {
  platform: Platform;
  selected: string | null;
  onChange: (ct: string | null) => void;
}

export function ContentTypeSelector({
  platform,
  selected,
  onChange,
}: ContentTypeSelectorProps) {
  const types = PLATFORM_CONTENT_TYPES[platform];

  const handleClick = (ct: string) => {
    // Clicking the active type deselects (null = let Genate choose)
    onChange(selected === ct ? null : ct);
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <span className="font-heading font-bold text-xs uppercase tracking-widest text-black">
          Content Type
        </span>
        {selected && (
          <button
            onClick={() => onChange(null)}
            className="text-xs font-heading text-gray-500 underline hover:text-black cursor-pointer"
          >
            Clear
          </button>
        )}
      </div>
      <div className="grid grid-cols-3 gap-2">
        {types.map((ct) => (
          <button
            key={ct}
            onClick={() => handleClick(ct)}
            className={`
              px-3 py-2 border-3 border-black text-xs font-heading font-bold uppercase
              tracking-wide transition-all duration-75 cursor-pointer text-left
              ${selected === ct
                ? "bg-brutal-yellow text-black shadow-brutal"
                : "bg-white text-black hover:bg-brutal-yellow/30 shadow-brutal-sm"
              }
            `}
          >
            {CONTENT_TYPE_LABELS[ct] ?? ct}
          </button>
        ))}
      </div>
      <p className="text-xs text-gray-500 font-body">
        {selected
          ? `Forcing: ${CONTENT_TYPE_LABELS[selected] ?? selected}`
          : "Unselected — Genate will choose automatically"}
      </p>
    </div>
  );
}
