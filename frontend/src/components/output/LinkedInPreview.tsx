"use client";

import React, { useState } from "react";
import type { LinkedInContent, PollContent } from "@/lib/types";

interface LinkedInPreviewProps {
  content?: LinkedInContent | null;
  pollContent?: PollContent | null;
}

export function LinkedInPreview({ content, pollContent }: LinkedInPreviewProps) {
  const [expanded, setExpanded] = useState(false);

  if (pollContent) {
    return (
      <div className="brutal-card p-5 flex flex-col gap-4">
        <PreviewHeader />
        {pollContent.intro && (
          <p className="font-body text-sm leading-relaxed">{pollContent.intro}</p>
        )}
        <p className="font-heading font-bold text-base">{pollContent.question}</p>
        <div className="flex flex-col gap-2">
          {pollContent.options.map((opt, i) => (
            <div
              key={i}
              className="border-3 border-black px-4 py-2 font-body text-sm bg-white hover:bg-brutal-yellow/30 cursor-pointer brutal-hover"
            >
              {opt}
            </div>
          ))}
        </div>
        {pollContent.duration && (
          <p className="text-xs text-gray-400 font-body">Duration: {pollContent.duration}</p>
        )}
      </div>
    );
  }

  if (!content) return null;

  const bodyLines = content.body.split("\n\n");
  const previewLines = expanded ? bodyLines : bodyLines.slice(0, 3);
  const shouldTruncate = bodyLines.length > 3;

  return (
    <div className="brutal-card p-5 flex flex-col gap-4">
      <PreviewHeader />

      {/* Hook */}
      <p className="font-heading font-bold text-base leading-snug">{content.hook}</p>

      {/* Body */}
      <div className="font-body text-sm leading-relaxed text-gray-800 flex flex-col gap-3">
        {previewLines.map((line, i) => (
          <p key={i}>{line}</p>
        ))}
        {shouldTruncate && !expanded && (
          <button
            onClick={() => setExpanded(true)}
            className="text-blue-600 text-sm font-body cursor-pointer hover:underline text-left"
          >
            ...see more
          </button>
        )}
      </div>

      {/* Hashtags */}
      <p className="font-body text-sm text-blue-600 font-medium">
        {content.hashtags.join(" ")}
      </p>
    </div>
  );
}

function PreviewHeader() {
  return (
    <div className="flex items-center gap-3">
      <div className="w-10 h-10 bg-brutal-yellow border-3 border-black flex items-center justify-center font-heading font-bold text-sm shrink-0">
        G
      </div>
      <div>
        <p className="font-heading font-bold text-sm">Genate AI</p>
        <p className="font-body text-xs text-gray-400">Marketing Content Platform</p>
      </div>
    </div>
  );
}
