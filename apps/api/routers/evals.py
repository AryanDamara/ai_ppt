"""
Evaluation router — admin-only endpoints for running LLM-as-Judge evaluations.

POST /api/v1/evals/run              — trigger an eval run
GET  /api/v1/evals/results/{run_id} — get eval results
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
import asyncio
from uuid import uuid4

from services.auth.jwt_validator import require_admin, AuthenticatedUser
from services.llmops.eval_runner import EvalRunner
from core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

# In-memory eval results store (production: use Redis or DB)
_eval_results: dict[str, dict] = {}


class EvalRunRequest(BaseModel):
    prompt_name: Optional[str] = None
    run_all:     bool = False


class EvalRunResponse(BaseModel):
    run_id:  str
    status:  str
    message: str


@router.post("/evals/run", response_model=EvalRunResponse)
async def trigger_eval_run(
    body: EvalRunRequest,
    background_tasks: BackgroundTasks,
    user: AuthenticatedUser = Depends(require_admin),
):
    """
    Trigger an evaluation run (admin only).
    Runs asynchronously and returns a run_id for polling.
    """
    run_id = str(uuid4())
    _eval_results[run_id] = {"status": "running", "results": []}

    async def run_evals():
        runner = EvalRunner()
        try:
            if body.run_all:
                from services.llmops.prompt_registry import get_registry
                registry = get_registry()
                prompts = [p["name"] for p in registry.list_prompts()
                          if "judge" not in p["name"]]
            elif body.prompt_name:
                prompts = [body.prompt_name]
            else:
                _eval_results[run_id] = {
                    "status": "failed",
                    "error": "Specify prompt_name or set run_all=true",
                }
                return

            all_results = []
            for prompt_name in prompts:
                summary = await runner.run_for_prompt(prompt_name)
                all_results.append(summary)

            _eval_results[run_id] = {
                "status": "complete",
                "results": all_results,
                "any_regression": any(r.get("regression_detected") for r in all_results),
            }
        except Exception as e:
            logger.error(f"Eval run {run_id} failed: {e}")
            _eval_results[run_id] = {"status": "failed", "error": str(e)}

    background_tasks.add_task(asyncio.ensure_future, run_evals())

    return EvalRunResponse(
        run_id=run_id,
        status="running",
        message="Evaluation started. Poll /evals/results/{run_id} for results.",
    )


@router.get("/evals/results/{run_id}")
async def get_eval_results(
    run_id: str,
    user: AuthenticatedUser = Depends(require_admin),
):
    """Get results of an eval run (admin only)."""
    if run_id not in _eval_results:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Eval run {run_id} not found")
    return _eval_results[run_id]
