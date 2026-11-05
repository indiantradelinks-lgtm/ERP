"""Run blocking, CPU-heavy work off the event loop.

The API serves every request on a single event loop, so any synchronous work
inside an `async def` route freezes EVERY other request while it runs. PDF
rendering (WeasyPrint) measured 0.8 s for a one-page PO and 5 s for a 300-row
report — long enough for queued requests to be cut at the edge, which the
browser shows as a Cloudflare "origin sent an empty response" error.

`run_blocking` pushes that work into a worker thread. The capacity limiter caps
how many heavy renders run at once so a burst of report downloads cannot
exhaust memory and get the container OOM-killed (another source of 520s).
"""
import functools
import logging
import time

import anyio

logger = logging.getLogger("erp.offload")

# Two concurrent renders: enough to keep downloads responsive, small enough to
# stay well inside the container's memory budget.
_RENDER_LIMITER = anyio.CapacityLimiter(2)
SLOW_MS = 1500


async def run_blocking(fn, *args, **kwargs):
    started = time.perf_counter()
    try:
        return await anyio.to_thread.run_sync(
            functools.partial(fn, *args, **kwargs), limiter=_RENDER_LIMITER)
    finally:
        ms = (time.perf_counter() - started) * 1000
        if ms > SLOW_MS:
            logger.warning(f"[offload] {getattr(fn, '__name__', fn)} took {ms:.0f} ms")
        if _RENDER_LIMITER.borrowed_tokens == 0:
            # Last heavy job finished — hand freed heap pages back to the OS so a
            # burst of exports does not leave the pod sitting at its RSS high-water mark.
            try:
                from system_health import trim_memory
                trim_memory()
            except Exception:  # noqa: BLE001
                pass
