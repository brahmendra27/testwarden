import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from flakelens.db import get_db
from flakelens.models import FailureAnalysis, TestResult
from flakelens.services.analysis import analyze_result
from flakelens.services.llm import llm_available

router = APIRouter(prefix="/api/v1", tags=["analysis"])


def _payload(analysis: FailureAnalysis, cached: bool) -> dict:
    return {
        "id": analysis.id,
        "result_id": analysis.result_id,
        "model": analysis.model,
        "content": analysis.content,
        "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
        "cached": cached,
    }


@router.get("/results/{result_id}/analysis")
def get_analysis(result_id: int, db: Session = Depends(get_db)):
    analysis = db.scalar(
        select(FailureAnalysis)
        .where(FailureAnalysis.result_id == result_id)
        .order_by(FailureAnalysis.id.desc())
    )
    return {
        "available": llm_available(),
        "analysis": _payload(analysis, cached=True) if analysis else None,
    }


@router.post("/results/{result_id}/analyze")
def analyze(result_id: int, force: bool = False, db: Session = Depends(get_db)):
    result = db.get(TestResult, result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Result not found")
    if result.status not in ("failed", "error") and not result.is_flaky_in_run:
        raise HTTPException(status_code=400, detail="Result has no failure to analyze")
    if not llm_available():
        raise HTTPException(
            status_code=503,
            detail="AI analysis unavailable: set ANTHROPIC_API_KEY or FLAKELENS_LLM_BASE_URL on the server",
        )
    existing = db.scalar(
        select(FailureAnalysis)
        .where(FailureAnalysis.result_id == result_id)
        .order_by(FailureAnalysis.id.desc())
    )
    try:
        analysis = analyze_result(db, result, force=force)
    except Exception as exc:  # network/auth errors surface as a clean 502
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {exc}")
    return _payload(analysis, cached=existing is not None and analysis.id == existing.id)
