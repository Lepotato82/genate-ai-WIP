import React from "react";
import { LinkedInPreview } from "./LinkedInPreview";
import { TwitterPreview } from "./TwitterPreview";
import { InstagramPreview } from "./InstagramPreview";
import type { GenerateResult } from "@/lib/types";

interface ContentPreviewProps {
  result: GenerateResult;
}

export function ContentPreview({ result }: ContentPreviewProps) {
  const fc = result.formatted_content;

  if (result.platform === "linkedin") {
    return (
      <LinkedInPreview
        content={fc.linkedin_content}
        pollContent={fc.linkedin_poll_content}
      />
    );
  }

  if (result.platform === "twitter") {
    return (
      <TwitterPreview
        content={fc.twitter_content}
        pollContent={fc.twitter_poll_content}
      />
    );
  }

  if (result.platform === "instagram") {
    return (
      <InstagramPreview
        content={fc.instagram_content}
        storyContent={fc.instagram_story_content}
      />
    );
  }

  if (result.platform === "blog" && fc.blog_content) {
    const blog = fc.blog_content as Record<string, unknown>;
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

  return (
    <div className="brutal-card p-5">
      <p className="font-body text-sm text-gray-500">No preview available.</p>
    </div>
  );
}
