from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.synthesis.synthesizer import stream_run

router = APIRouter(prefix="/stream", tags=["stream"])


@router.get("/{run_id}")
async def stream(run_id: str) -> StreamingResponse:
    async def event_source():
        async for chunk in stream_run(run_id):
            yield f"data: {chunk}\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")
