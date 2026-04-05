from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from agents import input_processor, ui_analyzer
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
