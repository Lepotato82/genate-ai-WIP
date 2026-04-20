from __future__ import annotations

import base64
import json
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from agents import compositor, input_processor, ui_analyzer
from pipeline import RUN_REGISTRY, approve_run, run_stream
from schemas.content_brief import PLATFORM_CONTENT_TYPES

app = FastAPI(title="Genate API", version="0.1.0")


class GenerateRequest(BaseModel):
    url: str
    platform: str = Field(default="linkedin")
    org_id: str | None = None
    user_document: str | None = None
    content_type: str | None = None

    @model_validator(mode="after")
    def validate_content_type(self) -> "GenerateRequest":
        if self.content_type is None:
            return self
        valid = PLATFORM_CONTENT_TYPES.get(self.platform, set())
        if self.content_type not in valid:
            raise ValueError(
                f"content_type='{self.content_type}' is not valid for "
                f"platform='{self.platform}'. Valid types: {sorted(valid)}"
            )
        return self


class ApproveRequest(BaseModel):
    edited_copy: str | None = None


class RerenderRequest(BaseModel):
    run_id: str
    slide_index: int
    headline: str
    body_text: str
    layout: str
    slide_label: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/analyze")
def analyze(url: str, org_id: str | None = None) -> dict[str, Any]:
    run_id = "analyze-preview"
    pkg = input_processor.run(url=url, run_id=run_id, org_id=org_id)
    brand = ui_analyzer.run(pkg)
    return {"run_id": run_id, "brand_profile": brand.model_dump()}


@app.post("/generate")
def generate(req: GenerateRequest) -> StreamingResponse:
    def stream():
        for evt in run_stream(
            url=req.url,
            platform=req.platform,
            org_id=req.org_id,
            user_document=req.user_document,
            force_content_type=req.content_type,
        ):
            yield f"data: {json.dumps(evt)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/rerender-slide")
def rerender_slide(req: RerenderRequest) -> dict[str, Any]:
    """Re-render a single slide with edited headline/body text.

    Looks up the BrandIdentity from RUN_REGISTRY so the compositor can apply
    the correct colors, fonts, and logo.  Returns a fresh base64 PNG.
    """
    if req.run_id not in RUN_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Run '{req.run_id}' not found in registry")

    artifacts = RUN_REGISTRY[req.run_id]
    if artifacts.brand_identity is None:
        raise HTTPException(status_code=422, detail="Brand identity not stored for this run")

    # Resolve canvas size from the stored composed images (fall back to default)
    canvas_size: tuple[int, int] = (1080, 1080)
    stored = artifacts.composed_images or {}
    slides_list = stored.get("composed_images", [])
    if slides_list:
        first = slides_list[0]
        canvas_size = (first.get("width", 1080), first.get("height", 1080))

    png_bytes = compositor._compose_slide(
        headline=req.headline,
        subtext=req.body_text,
        slide_label=req.slide_label,
        identity=artifacts.brand_identity,
        layout=req.layout,
        canvas_size=canvas_size,
    )

    return {
        "png_b64": base64.b64encode(png_bytes).decode("ascii"),
        "layout": req.layout,
    }


@app.post("/runs/{run_id}/approve")
def approve(run_id: str, req: ApproveRequest) -> dict[str, Any]:
    try:
        resp = approve_run(run_id=run_id, edited_copy=req.edited_copy)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    artifacts = RUN_REGISTRY[run_id]
    return {
        **resp,
        "stored": {
            "brand_profile": artifacts.brand_profile.model_dump(),
            "product_knowledge": artifacts.product_knowledge.model_dump(),
            "strategy_brief": artifacts.strategy_brief.model_dump(),
        },
    }
