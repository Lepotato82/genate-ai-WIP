"use client";

import React, { useEffect, useState } from "react";
import { LinkedInPreview } from "./LinkedInPreview";
import { TwitterPreview } from "./TwitterPreview";
import { InstagramPreview } from "./InstagramPreview";
import { rerenderSlide } from "@/lib/api";
import type { ComposedImage, CompositorResult, GenerateResult, LayoutArchetype } from "@/lib/types";

interface ContentPreviewProps {
  result: GenerateResult;
}

export function ContentPreview({ result }: ContentPreviewProps) {
  const fc = result.formatted_content;
  const ci = result.composed_images;
  const hasImages =
    ci?.compositor_enabled === true &&
    ci.composed_images.length > 0 &&
    ci.composed_images[0].png_b64 !== "";

  return (
    <div className="flex flex-col gap-4">
      {/* Composed image panel — above text preview */}
      {hasImages && ci && (
        <ComposedImagePanel
          images={ci.composed_images}
          layout={ci.layout}
          contentType={result.content_type}
          runId={result.run_id}
        />
      )}

      {/* Platform text previews */}
      {result.platform === "linkedin" && (
        <LinkedInPreview
          content={fc.linkedin_content}
          pollContent={fc.linkedin_poll_content}
        />
      )}

      {result.platform === "twitter" && (
        <TwitterPreview
          content={fc.twitter_content}
          pollContent={fc.twitter_poll_content}
        />
      )}

      {result.platform === "instagram" && (
        <InstagramPreview
          content={fc.instagram_content}
          storyContent={fc.instagram_story_content}
        />
      )}

      {result.platform === "blog" && fc.blog_content && (
        <BlogPreview blog={fc.blog_content as Record<string, unknown>} />
      )}

      {!["linkedin", "twitter", "instagram", "blog"].includes(result.platform) && (
        <div className="brutal-card p-5">
          <p className="font-body text-sm text-gray-500">No preview available.</p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Composed Image Panel  (with inline slide editor)
// ---------------------------------------------------------------------------

function ComposedImagePanel({
  images,
  layout,
  contentType,
  runId,
}: {
  images: ComposedImage[];
  layout: LayoutArchetype | null;
  contentType?: string;
  runId: string;
}) {
  const [activeIdx, setActiveIdx] = useState(0);
  // Local copies of slides so re-renders update only the affected slide
  const [localImages, setLocalImages] = useState<ComposedImage[]>(images);
  const [editHeadline, setEditHeadline] = useState("");
  const [editBody, setEditBody] = useState("");
  const [isRendering, setIsRendering] = useState(false);
  const [rerenderError, setRerenderError] = useState<string | null>(null);

  const isCarousel = localImages.length > 1;
  const active = localImages[activeIdx];

  // Sync edit fields when the active slide changes
  useEffect(() => {
    const slide = localImages[activeIdx];
    setEditHeadline(slide?.headline ?? "");
    setEditBody(slide?.body_text ?? "");
    setRerenderError(null);
  }, [activeIdx, localImages]);

  const handleRerender = async () => {
    if (isRendering) return;
    setIsRendering(true);
    setRerenderError(null);
    try {
      const result = await rerenderSlide({
        run_id: runId,
        slide_index: active.slide_index,
        headline: editHeadline,
        body_text: editBody,
        layout: active.layout,
        slide_label: active.slide_label ?? null,
      });
      setLocalImages((prev) =>
        prev.map((img, i) =>
          i === activeIdx ? { ...img, png_b64: result.png_b64 } : img,
        ),
      );
    } catch (err) {
      setRerenderError(err instanceof Error ? err.message : "Re-render failed");
    } finally {
      setIsRendering(false);
    }
  };

  const handleDownload = () => {
    const a = document.createElement("a");
    a.href = `data:image/png;base64,${active.png_b64}`;
    a.download = `slide-${active.slide_index + 1}.png`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  return (
    <div className="brutal-card overflow-hidden">
      {/* Label bar */}
      <div className="px-4 pt-3 pb-2 border-b-3 border-black flex items-center justify-between bg-brutal-yellow">
        <span className="font-heading font-bold text-xs uppercase tracking-widest text-black">
          Brand Image · {contentType ?? "auto"} · {active.layout ?? layout ?? "auto"}
        </span>
        {isCarousel && (
          <span className="font-body text-xs text-black font-medium">
            {activeIdx + 1} / {localImages.length}
          </span>
        )}
      </div>

      {/* Main image display */}
      <div
        className={`bg-gray-100 flex items-center justify-center relative transition-opacity ${
          isRendering ? "opacity-50" : ""
        }`}
      >
        {isRendering && (
          <div className="absolute inset-0 flex items-center justify-center z-10">
            <span className="bg-black text-brutal-yellow font-heading font-bold text-xs uppercase tracking-widest px-3 py-1.5">
              Rendering…
            </span>
          </div>
        )}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`data:image/png;base64,${active.png_b64}`}
          alt={`Composed slide ${activeIdx + 1}`}
          className="w-full h-auto block"
          style={{ maxHeight: "520px", objectFit: "contain" }}
        />
      </div>

      {/* Carousel thumbnail strip */}
      {isCarousel && (
        <div className="flex gap-2 p-3 overflow-x-auto border-t-3 border-black bg-white">
          {localImages.map((img, i) => (
            <button
              key={i}
              onClick={() => setActiveIdx(i)}
              className={`shrink-0 w-16 h-16 border-3 overflow-hidden cursor-pointer transition-all
                ${
                  i === activeIdx
                    ? "border-black shadow-brutal-sm"
                    : "border-gray-300 hover:border-gray-500"
                }`}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`data:image/png;base64,${img.png_b64}`}
                alt={`Slide ${i + 1}`}
                className="w-full h-full object-cover"
              />
            </button>
          ))}
        </div>
      )}

      {/* ── Slide Editor ── */}
      <div className="border-t-3 border-black">
        {/* Editor header */}
        <div className="px-4 py-2.5 bg-black flex items-center justify-between">
          <span className="font-heading font-bold text-xs uppercase tracking-widest text-brutal-yellow">
            Edit Slide {activeIdx + 1}
          </span>
          <span className="font-body text-xs text-gray-400 normal-case">
            {active.layout}
          </span>
        </div>

        {/* Inputs */}
        <div className="p-4 bg-white flex flex-col gap-3">
          <div>
            <label className="block font-heading font-bold text-xs uppercase tracking-wide text-gray-500 mb-1">
              Headline
            </label>
            <input
              type="text"
              value={editHeadline}
              onChange={(e) => setEditHeadline(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleRerender()}
              className="w-full border-3 border-black px-3 py-2 font-body text-sm focus:outline-none focus:bg-yellow-50"
              placeholder="Slide headline…"
            />
          </div>

          <div>
            <label className="block font-heading font-bold text-xs uppercase tracking-wide text-gray-500 mb-1">
              Body Text
            </label>
            <textarea
              value={editBody}
              onChange={(e) => setEditBody(e.target.value)}
              rows={3}
              className="w-full border-3 border-black px-3 py-2 font-body text-sm focus:outline-none focus:bg-yellow-50 resize-none"
              placeholder="Supporting body text…"
            />
          </div>

          {rerenderError && (
            <p className="font-body text-xs text-red-600">{rerenderError}</p>
          )}

          {/* Action buttons */}
          <div className="flex gap-3">
            <button
              onClick={handleRerender}
              disabled={isRendering}
              className={`border-3 border-black px-4 py-2 font-heading font-bold text-xs uppercase tracking-wide transition-all active:translate-y-px
                ${
                  isRendering
                    ? "bg-gray-100 text-gray-400 cursor-not-allowed"
                    : "bg-brutal-yellow hover:shadow-brutal-sm cursor-pointer"
                }`}
            >
              {isRendering ? "Rendering…" : "Re-render ↺"}
            </button>
            <button
              onClick={handleDownload}
              className="border-3 border-black px-4 py-2 font-heading font-bold text-xs uppercase tracking-wide bg-white hover:shadow-brutal-sm active:translate-y-px cursor-pointer transition-all"
            >
              Download PNG ↓
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Blog preview (unchanged from original)
// ---------------------------------------------------------------------------

function BlogPreview({ blog }: { blog: Record<string, unknown> }) {
  return (
    <div className="brutal-card p-5 flex flex-col gap-4">
      <h2 className="font-heading font-bold text-xl">
        {String(blog.title ?? "Blog Post")}
      </h2>
      <p className="font-body text-sm text-gray-600 italic">
        {String(blog.meta_description ?? "")}
      </p>
      <div className="border-t-3 border-black pt-4">
        <p className="font-body text-sm leading-relaxed whitespace-pre-wrap">
          {String(blog.body ?? "")}
        </p>
      </div>
    </div>
  );
}
