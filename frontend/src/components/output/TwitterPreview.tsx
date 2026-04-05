import React from "react";
import type { TwitterContent, PollContent } from "@/lib/types";

interface TwitterPreviewProps {
  content?: TwitterContent | null;
  pollContent?: PollContent | null;
}

export function TwitterPreview({ content, pollContent }: TwitterPreviewProps) {
  if (pollContent) {
    return (
      <div className="brutal-card p-5 flex flex-col gap-4">
        <TweetHeader />
        <p className="font-heading font-bold text-base">{pollContent.question}</p>
        <div className="flex flex-col gap-2">
          {pollContent.options.map((opt, i) => (
            <div
              key={i}
              className="border-3 border-black px-4 py-2 font-body text-sm bg-white hover:bg-blue-50 cursor-pointer"
            >
              {opt}
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!content || content.tweets.length === 0) return null;

  return (
    <div className="flex flex-col">
      {content.tweets.map((tweet, i) => (
        <div key={i} className="flex gap-3">
          {/* Thread line */}
          <div className="flex flex-col items-center">
            <div className="w-8 h-8 bg-brutal-yellow border-3 border-black flex items-center justify-center font-heading font-bold text-xs shrink-0">
              G
            </div>
            {i < content.tweets.length - 1 && (
              <div className="w-0.5 flex-1 bg-black my-1 min-h-4" />
            )}
          </div>

          {/* Tweet content */}
          <div className={`flex-1 pb-4 ${i < content.tweets.length - 1 ? "" : ""}`}>
            <div className="flex items-baseline gap-2 mb-1">
              <span className="font-heading font-bold text-sm">Genate AI</span>
              <span className="font-body text-xs text-gray-400">@genate_ai</span>
            </div>
            <p className="font-body text-sm leading-relaxed">{tweet}</p>
            <p className="font-body text-xs text-gray-400 mt-1">
              {content.tweet_char_counts[i]} chars
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

function TweetHeader() {
  return (
    <div className="flex items-center gap-3">
      <div className="w-8 h-8 bg-brutal-yellow border-3 border-black flex items-center justify-center font-heading font-bold text-xs shrink-0">
        G
      </div>
      <div>
        <span className="font-heading font-bold text-sm">Genate AI</span>
        <span className="font-body text-xs text-gray-400 ml-2">@genate_ai</span>
      </div>
    </div>
  );
}
