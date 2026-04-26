"""/api/v1/runs — list, detail, manual trigger."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from elise_leads.api.deps import get_session
from elise_leads.api.schemas.run import (
    RunDetail,
    RunListItem,
    RunListResponse,
)
from elise_leads.api.schemas.run import RunTriggerResponse
from elise_leads.cron import create_run, execute_run
from elise_leads.enrichers._http import log
from elise_leads.models import Run

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("", response_model=RunListResponse, summary="Run history")
async def list_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="success | partial | crashed | running",
    ),
    session: AsyncSession = Depends(get_session),
) -> RunListResponse:
    base_q = select(Run)
    count_q = select(func.count(Run.id))
    if status_filter:
        base_q = base_q.where(Run.status == status_filter)
        count_q = count_q.where(Run.status == status_filter)

    total = (await session.execute(count_q)).scalar_one()

    rows = (
        await session.execute(
            base_q.order_by(desc(Run.started_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return RunListResponse(
        runs=[RunListItem.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{run_id}",
    response_model=RunDetail,
    summary="Run detail (with rendered MD report)",
)
async def get_run(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> RunDetail:
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Run not found")
    return RunDetail.model_validate(run)


@router.post(
    "/trigger",
    response_model=RunTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually trigger pipeline (background task)",
)
async def trigger_run(
    background: BackgroundTasks,
) -> RunTriggerResponse:
    """Create a Run row and schedule pipeline execution as a background task.

    Returns immediately with the run_id so the dashboard can start polling
    GET /runs/{run_id} for status/progress.
    """
    run_id = await create_run()
    log.info("api.run.triggered", run_id=str(run_id))

    # Schedule background execution. We use asyncio.create_task so it survives
    # past the response, but FastAPI's BackgroundTasks would also work here.
    async def _bg() -> None:
        try:
            await execute_run(run_id)
        except Exception as exc:
            log.error(
                "api.run.bg_failed",
                run_id=str(run_id),
                error=type(exc).__name__,
            )

    background.add_task(_bg)
    return RunTriggerResponse(run_id=run_id)
