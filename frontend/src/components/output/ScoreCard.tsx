import React from "react";
import type { EvaluatorOutput } from "@/lib/types";

interface ScoreBarProps {
  label: string;
  score: number;
}

function ScoreBar({ label, score }: ScoreBarProps) {
  const fill =
    score >= 4
      ? "bg-brutal-green"
      : score >= 3
        ? "bg-brutal-yellow"
        : "bg-brutal-orange";
  const pct = (score / 5) * 100;

  return (
    <div className="flex items-center gap-3">
      <span className="font-heading font-bold text-xs uppercase tracking-wide w-24 shrink-0">
        {label}
      </span>
      <div className="flex-1 h-4 border-3 border-black bg-gray-100 relative overflow-hidden">
        <div
          className={`h-full ${fill} transition-all duration-500`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="font-heading font-bold text-sm w-8 text-right tabular-nums">
        {score}/5
      </span>
    </div>
  );
}

interface ScoreCardProps {
  scores: EvaluatorOutput;
}

export function ScoreCard({ scores }: ScoreCardProps) {
  return (
    <div className="brutal-card p-5 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h3 className="font-heading font-bold text-sm uppercase tracking-widest">
          Eval Scores
        </h3>
        <span
          className={`
            border-3 border-black px-3 py-1 font-heading font-bold text-sm
            ${scores.passes ? "bg-brutal-yellow" : "bg-brutal-orange text-white"}
          `}
        >
          {scores.passes ? "✓ Passed" : "✗ Failed"}
        </span>
      </div>

      <div className="flex flex-col gap-3">
        <ScoreBar label="Clarity" score={scores.clarity} />
        <ScoreBar label="Engagement" score={scores.engagement} />
        <ScoreBar label="Tone Match" score={scores.tone_match} />
        <ScoreBar label="Accuracy" score={scores.accuracy} />
      </div>

      <div className="border-t-3 border-black pt-3 flex items-center justify-between">
        <span className="font-heading text-xs uppercase tracking-wide text-gray-500">
          Overall
        </span>
        <span className="font-heading font-bold text-xl tabular-nums">
          {scores.overall_score.toFixed(1)} / 5.0
        </span>
      </div>

      {scores.scores_rationale && (
        <p className="text-xs font-body text-gray-600 border-t border-gray-200 pt-3">
          {scores.scores_rationale}
        </p>
      )}
    </div>
  );
}
