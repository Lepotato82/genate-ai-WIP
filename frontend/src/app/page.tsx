"use client";

import React, { useState } from "react";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { PlatformSelector } from "@/components/input/PlatformSelector";
import { ContentTypeSelector } from "@/components/input/ContentTypeSelector";
import { StepProgress } from "@/components/pipeline/StepProgress";
import { ContentPreview } from "@/components/output/ContentPreview";
import { ScoreCard } from "@/components/output/ScoreCard";
import { streamGenerate } from "@/lib/api";
import type { AppState, GenerateResult, Platform, SSEEvent } from "@/lib/types";

export default function Page() {
  const [state, setState] = useState<AppState>({ mode: "input" });
  const [url, setUrl] = useState("");
  const [platform, setPlatform] = useState<Platform>("linkedin");
  const [contentType, setContentType] = useState<string | null>(null);
  const [urlError, setUrlError] = useState("");
  const [copied, setCopied] = useState(false);

  // Reset content type when platform changes
  const handlePlatformChange = (p: Platform) => {
    setPlatform(p);
    setContentType(null);
  };

  const handleGenerate = () => {
    const trimmed = url.trim();
    if (!trimmed) {
      setUrlError("Please enter a URL");
      return;
    }
    if (!trimmed.startsWith("http://") && !trimmed.startsWith("https://")) {
      setUrlError("URL must start with http:// or https://");
      return;
    }
    setUrlError("");
    setState({ mode: "generating", events: [] });

    streamGenerate(
      {
        url: trimmed,
        platform,
        content_type: contentType ?? undefined,
      },
      (event: SSEEvent) => {
        setState((prev) =>
          prev.mode === "generating"
            ? { ...prev, events: [...prev.events, event] }
            : prev,
        );
      },
      (result: GenerateResult) => {
        setState((prev) =>
          prev.mode === "generating"
            ? {
                mode: "result",
                runId: result.run_id,
                events: prev.events,
                result,
              }
            : prev,
        );
      },
      (error: Error) => {
        console.error("Generation error:", error);
        setState({ mode: "input" });
        setUrlError(`Generation failed: ${error.message}`);
      },
    );
  };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const handleReset = () => {
    setState({ mode: "input" });
    setCopied(false);
  };

  // ── Input state ─────────────────────────────────────────────────────────
  if (state.mode === "input") {
    return (
      <main className="min-h-screen bg-brutal-bg">
        {/* Header */}
        <header className="border-b-3 border-black bg-brutal-yellow">
          <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="bg-black text-brutal-yellow px-3 py-1 font-heading font-bold text-xl uppercase tracking-wider">
                GENATE
              </div>
            </div>
            <p className="font-heading text-xs uppercase tracking-widest text-black hidden sm:block">
              AI Content Pipeline for SaaS
            </p>
          </div>
        </header>

        {/* Hero */}
        <section className="border-b-3 border-black bg-white">
          <div className="max-w-4xl mx-auto px-6 py-12">
            <h1 className="font-heading font-bold text-4xl sm:text-5xl leading-none uppercase mb-4">
              Generate brand-native
              <br />
              <span className="bg-brutal-yellow px-2">SaaS content</span>
              <br />
              from any URL.
            </h1>
            <p className="font-body text-base text-gray-600 max-w-xl">
              Paste your product URL. Genate reads your CSS, extracts brand
              identity, and generates platform-ready copy grounded in your real
              proof points.
            </p>
          </div>
        </section>

        {/* Form */}
        <section className="max-w-4xl mx-auto px-6 py-10">
          <div className="brutal-card p-6 sm:p-8 flex flex-col gap-7">
            {/* URL input */}
            <BrutalInput
              label="Product URL"
              type="url"
              placeholder="https://yourproduct.com"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              error={urlError}
              onKeyDown={(e) => e.key === "Enter" && handleGenerate()}
            />

            {/* Platform */}
            <PlatformSelector selected={platform} onChange={handlePlatformChange} />

            {/* Content type */}
            <ContentTypeSelector
              platform={platform}
              selected={contentType}
              onChange={setContentType}
            />

            {/* Generate button */}
            <BrutalButton
              size="lg"
              onClick={handleGenerate}
              className="w-full"
            >
              Generate Content →
            </BrutalButton>
          </div>
        </section>

        {/* Footer */}
        <footer className="border-t-3 border-black mt-auto">
          <div className="max-w-4xl mx-auto px-6 py-4">
            <p className="font-body text-xs text-gray-400">
              Built for Indian SaaS · Genate v0.1
            </p>
          </div>
        </footer>
      </main>
    );
  }

  // ── Generating state ─────────────────────────────────────────────────────
  if (state.mode === "generating") {
    const displayUrl = url.replace(/^https?:\/\//, "").split("/")[0];
    return (
      <main className="min-h-screen bg-brutal-bg">
        <header className="border-b-3 border-black bg-black text-brutal-yellow">
          <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
            <div className="font-heading font-bold text-xl uppercase tracking-wider">
              GENATE
            </div>
            <div className="flex items-center gap-2 font-body text-sm">
              <span className="inline-block w-2 h-2 bg-brutal-yellow animate-pulse" />
              Generating for{" "}
              <span className="font-heading font-bold">{displayUrl}</span>
            </div>
          </div>
        </header>

        <section className="max-w-4xl mx-auto px-6 py-10 flex flex-col gap-6">
          <div className="flex items-center justify-between">
            <h2 className="font-heading font-bold text-2xl uppercase">
              Pipeline Running
            </h2>
            <BrutalButton variant="secondary" size="sm" onClick={handleReset}>
              ← Cancel
            </BrutalButton>
          </div>

          <StepProgress events={state.events} />

          <p className="font-body text-xs text-gray-400">
            Running {state.events.length} step
            {state.events.length !== 1 ? "s" : ""}…
          </p>
        </section>
      </main>
    );
  }

  // ── Result state ─────────────────────────────────────────────────────────
  const { result } = state;
  const fc = result.formatted_content;

  // Get full text for copy button
  const fullText = (() => {
    if (fc.linkedin_content) return fc.linkedin_content.full_post;
    if (fc.twitter_content) return fc.twitter_content.tweets.join("\n\n");
    if (fc.instagram_content) return fc.instagram_content.full_caption;
    if (fc.instagram_story_content)
      return `${fc.instagram_story_content.hook}\n${fc.instagram_story_content.cta_text}`;
    if (fc.linkedin_poll_content)
      return `${fc.linkedin_poll_content.question}\n${fc.linkedin_poll_content.options.join("\n")}`;
    if (fc.twitter_poll_content)
      return `${fc.twitter_poll_content.question}\n${fc.twitter_poll_content.options.join("\n")}`;
    return JSON.stringify(fc.blog_content ?? "", null, 2);
  })();

  const displayUrl = url.replace(/^https?:\/\//, "").split("/")[0];

  return (
    <main className="min-h-screen bg-brutal-bg">
      <header className="border-b-3 border-black bg-brutal-yellow">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="bg-black text-brutal-yellow px-3 py-1 font-heading font-bold text-xl uppercase tracking-wider">
            GENATE
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`border-3 border-black px-3 py-1 font-heading font-bold text-xs uppercase ${
                result.passes ? "bg-white" : "bg-brutal-orange text-white"
              }`}
            >
              {result.passes ? "✓ Passed" : "✗ Needs revision"}
            </span>
          </div>
        </div>
      </header>

      <section className="max-w-5xl mx-auto px-6 py-8 flex flex-col gap-4">
        {/* Title row */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h2 className="font-heading font-bold text-2xl uppercase">
              {result.platform.charAt(0).toUpperCase() + result.platform.slice(1)}{" "}
              · {displayUrl}
            </h2>
            <p className="font-body text-xs text-gray-400 mt-1">
              Run ID: {result.run_id.slice(0, 8)}…
            </p>
          </div>
          <div className="flex gap-3">
            <BrutalButton
              variant="secondary"
              size="sm"
              onClick={() => handleCopy(fullText)}
            >
              {copied ? "Copied!" : "Copy →"}
            </BrutalButton>
            <BrutalButton size="sm" onClick={handleReset}>
              ← New
            </BrutalButton>
          </div>
        </div>

        {/* Two-column layout */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6 items-start">
          {/* Preview */}
          <div>
            <ContentPreview result={result} />
          </div>

          {/* Scores + pipeline summary */}
          <div className="flex flex-col gap-4">
            <ScoreCard scores={result.evaluator_output} />

            {/* Pipeline summary */}
            <div className="brutal-card p-4">
              <h3 className="font-heading font-bold text-xs uppercase tracking-widest mb-3">
                Pipeline ({state.events.length} steps)
              </h3>
              <div className="flex flex-col gap-1">
                {state.events
                  .filter((e) => e.status === "complete")
                  .map((e, i) => (
                    <div
                      key={i}
                      className="flex justify-between font-body text-xs text-gray-600"
                    >
                      <span className="capitalize">
                        {e.agent.replace(/_/g, " ")}
                      </span>
                      <span className="tabular-nums">{e.elapsed.toFixed(1)}s</span>
                    </div>
                  ))}
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
