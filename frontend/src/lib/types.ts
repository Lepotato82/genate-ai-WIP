// ---------------------------------------------------------------------------
// Platform + Content Type definitions
// Mirrors PLATFORM_CONTENT_TYPES in schemas/content_brief.py
// ---------------------------------------------------------------------------

export type Platform = "linkedin" | "twitter" | "instagram" | "blog";

export const PLATFORM_CONTENT_TYPES: Record<Platform, string[]> = {
  linkedin: [
    "carousel",
    "text_post",
    "multi_image",
    "short_video",
    "poll",
    "question_post",
    "single_image",
  ],
  twitter: ["thread", "single_tweet", "poll"],
  instagram: ["carousel", "reel", "single_image", "story", "collab_post"],
  blog: [
    "how_to",
    "case_study",
    "thought_leadership",
    "product_led_seo",
    "comparison",
    "listicle",
    "original_research",
    "use_case",
    "glossary",
    "checklist",
    "changelog",
  ],
};

export const CONTENT_TYPE_LABELS: Record<string, string> = {
  // LinkedIn
  carousel: "Carousel",
  text_post: "Text Post",
  multi_image: "Multi Image",
  short_video: "Short Video",
  poll: "Poll",
  question_post: "Question Post",
  single_image: "Single Image",
  // Twitter
  thread: "Thread",
  single_tweet: "Single Tweet",
  // Instagram
  reel: "Reel",
  story: "Story",
  collab_post: "Collab Post",
  // Blog
  how_to: "How-To",
  case_study: "Case Study",
  thought_leadership: "Thought Leadership",
  product_led_seo: "Product-Led SEO",
  comparison: "Comparison",
  listicle: "Listicle",
  original_research: "Original Research",
  use_case: "Use Case",
  glossary: "Glossary",
  checklist: "Checklist",
  changelog: "Changelog",
};

export const PLATFORM_LABELS: Record<Platform, string> = {
  linkedin: "LinkedIn",
  twitter: "Twitter / X",
  instagram: "Instagram",
  blog: "Blog",
};

// ---------------------------------------------------------------------------
// API request / response types
// ---------------------------------------------------------------------------

export interface GenerateRequest {
  url: string;
  platform: Platform;
  content_type?: string;
  org_id?: string;
}

// SSE event yielded by pipeline.run_stream()
export interface SSEEvent {
  step: number;
  agent: string;
  status: string;
  elapsed: number;
  message: string;
  // Present on the final pipeline:complete event
  run_id?: string;
  passes?: boolean;
  formatted_content?: FormattedContentRaw;
  evaluator_output?: EvaluatorOutput;
  composed_images?: CompositorResult;
  // Diagnostic fields
  content_type?: string;
  logo_confidence?: string | null;
  logo_compositing_enabled?: boolean;
  design_category?: string;
}

// ---------------------------------------------------------------------------
// FormattedContent (subset used by the frontend)
// ---------------------------------------------------------------------------

export interface LinkedInContent {
  hook: string;
  body: string;
  hashtags: string[];
  full_post: string;
}

export interface TwitterContent {
  tweets: string[];
  tweet_char_counts: number[];
  hashtags: string[];
}

export interface InstagramContent {
  preview_text: string;
  body: string;
  hashtags: string[];
  full_caption: string;
}

export interface InstagramStoryContent {
  hook: string;
  cta_text: string;
}

export interface PollContent {
  intro: string | null;
  question: string;
  options: string[];
  duration: string | null;
}

export interface FormattedContentRaw {
  run_id: string;
  platform: string;
  linkedin_content?: LinkedInContent | null;
  twitter_content?: TwitterContent | null;
  instagram_content?: InstagramContent | null;
  instagram_story_content?: InstagramStoryContent | null;
  linkedin_poll_content?: PollContent | null;
  twitter_poll_content?: PollContent | null;
  blog_content?: Record<string, unknown> | null;
}

export interface EvaluatorOutput {
  platform: string;
  clarity: number;
  engagement: number;
  tone_match: number;
  accuracy: number;
  overall_score: number;
  passes: boolean;
  revision_hint: string | null;
  scores_rationale: string;
  retry_count: number;
}

// ---------------------------------------------------------------------------
// Compositor output types
// ---------------------------------------------------------------------------

export type LayoutArchetype =
  | "typographic"
  | "bold_block"
  | "sidebar"
  | "frame"
  | "hero_text"
  | "split_field"
  | "diagonal_split"
  | "editorial_photo"
  | "photo_overlay"
  | "risograph"
  | "soft_card"
  | "stat_hero";

export interface ComposedImage {
  slide_index: number;
  /** Base64-encoded PNG bytes. Render as: <img src={`data:image/png;base64,${png_b64}`} /> */
  png_b64: string;
  width: number;
  height: number;
  layout: LayoutArchetype;
  /** Source text used when compositing — enables the slide editor to pre-populate inputs */
  headline?: string;
  body_text?: string;
  slide_label?: string | null;
}

// ---------------------------------------------------------------------------
// Slide re-render (canvas editor)
// ---------------------------------------------------------------------------

export interface RerenderRequest {
  run_id: string;
  slide_index: number;
  headline: string;
  body_text: string;
  layout: string;
  slide_label?: string | null;
}

export interface RerenderResponse {
  png_b64: string;
  layout: string;
}

export interface CompositorResult {
  composed_images: ComposedImage[];
  layout: LayoutArchetype | null;
  slide_count: number;
  compositor_enabled: boolean;
  error: string | null;
}

// ---------------------------------------------------------------------------
// App-level result type assembled from the final SSE event
// ---------------------------------------------------------------------------

export interface GenerateResult {
  run_id: string;
  platform: Platform;
  content_type: string;
  formatted_content: FormattedContentRaw;
  evaluator_output: EvaluatorOutput;
  passes: boolean;
  composed_images?: CompositorResult;
  // Diagnostic fields from the pipeline done event
  logo_confidence?: string | null;
  logo_compositing_enabled?: boolean;
  design_category?: string;
}

// ---------------------------------------------------------------------------
// App state machine
// ---------------------------------------------------------------------------

export type AppState =
  | { mode: "input" }
  | { mode: "generating"; events: SSEEvent[] }
  | { mode: "result"; runId: string; events: SSEEvent[]; result: GenerateResult };
