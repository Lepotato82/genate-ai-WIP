"use client";

import React, { useState } from "react";
import type { InstagramContent, InstagramStoryContent } from "@/lib/types";

interface InstagramPreviewProps {
  content?: InstagramContent | null;
  storyContent?: InstagramStoryContent | null;
}

export function InstagramPreview({ content, storyContent }: InstagramPreviewProps) {
  const [showCaption, setShowCaption] = useState(false);

  if (storyContent) {
    return (
      <div className="brutal-card overflow-hidden">
        {/* Story slide */}
        <div className="aspect-[9/16] max-h-96 bg-brutal-yellow border-b-3 border-black flex flex-col items-center justify-center p-8 gap-6">
          <p className="font-heading font-bold text-2xl text-center leading-tight text-black">
            {storyContent.hook}
          </p>
          <div className="border-3 border-black bg-black text-brutal-yellow px-6 py-2 font-heading font-bold text-sm uppercase">
            {storyContent.cta_text}
          </div>
        </div>
        <div className="p-4">
          <p className="font-heading font-bold text-xs uppercase tracking-widest text-gray-400">
            Instagram Story
          </p>
        </div>
      </div>
    );
  }

  if (!content) return null;

  return (
    <div className="brutal-card overflow-hidden">
      {/* Square preview */}
      <div className="aspect-square bg-brutal-yellow border-b-3 border-black flex items-center justify-center p-8">
        <p className="font-heading font-bold text-xl text-center leading-tight">
          {content.preview_text}
        </p>
      </div>

      {/* Caption */}
      <div className="p-4 flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 bg-black text-brutal-yellow flex items-center justify-center font-heading font-bold text-xs border-3 border-black">
            G
          </div>
          <span className="font-heading font-bold text-sm">genate.ai</span>
        </div>

        <div className="font-body text-sm text-gray-800">
          <p>{content.preview_text}</p>
          {showCaption && (
            <p className="mt-2 whitespace-pre-line leading-relaxed">{content.body}</p>
          )}
          <button
            onClick={() => setShowCaption((v) => !v)}
            className="text-gray-400 text-sm mt-1 cursor-pointer hover:text-black"
          >
            {showCaption ? "less" : "more"}
          </button>
        </div>

        <p className="font-body text-xs text-blue-600 leading-relaxed">
          {content.hashtags.slice(0, 10).join(" ")}
          {content.hashtags.length > 10 && (
            <span className="text-gray-400"> +{content.hashtags.length - 10} more</span>
          )}
        </p>
      </div>
    </div>
  );
}
