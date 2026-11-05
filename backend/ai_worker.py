"""LLM calls in a short-lived subprocess.

`emergentintegrations` pulls in litellm (~160 MB RSS) and never releases it, which
on a 512 Mi pod was the proven trigger for OOMKills. Every AI call therefore runs in
a child process that exits when the reply is back; the API process never imports
litellm. Concurrency is capped so two AI calls cannot double that peak.

    reply = await llm_send("gemini", "gemini-2.5-pro", system_msg, text,
                           files=[{"path": "/tmp/x.pdf", "mime": "application/pdf"}])
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time

logger = logging.getLogger("erp.ai")

_SEM = asyncio.Semaphore(int(os.environ.get("AI_WORKER_CONCURRENCY", "1")))
TIMEOUT_S = int(os.environ.get("AI_WORKER_TIMEOUT", "300"))


class AIWorkerError(RuntimeError):
    pass


async def llm_send(provider: str, model: str, system_message: str, text: str,
                   files: list[dict] | None = None, session_id: str | None = None) -> str:
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise AIWorkerError("EMERGENT_LLM_KEY is not configured")
    job = {"provider": provider, "model": model, "system_message": system_message, "text": text,
           "files": files or [], "session_id": session_id or f"{provider}-{int(time.time())}", "api_key": key}
    started = time.perf_counter()
    async with _SEM:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, __file__, cwd=os.path.dirname(os.path.abspath(__file__)),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(proc.communicate(json.dumps(job).encode()), timeout=TIMEOUT_S)
        except asyncio.TimeoutError:
            proc.kill()
            raise AIWorkerError(f"AI call timed out after {TIMEOUT_S}s")
    ms = (time.perf_counter() - started) * 1000
    try:
        res = json.loads(out.decode() or "{}")
    except json.JSONDecodeError:
        res = {}
    if not res.get("ok"):
        detail = res.get("error") or err.decode(errors="ignore")[-600:] or f"exit {proc.returncode}"
        logger.warning("[ai-worker] %s/%s failed in %.0f ms: %s", provider, model, ms, detail[:300])
        raise AIWorkerError(detail)
    logger.info("[ai-worker] %s/%s ok in %.0f ms (peak %s MB)", provider, model, ms, res.get("peak_mb"))
    return res.get("reply") or ""


def _run_job(job: dict) -> dict:
    from emergentintegrations.llm.chat import FileContentWithMimeType, LlmChat, UserMessage
    chat = LlmChat(api_key=job["api_key"], session_id=job["session_id"],
                   system_message=job["system_message"]).with_model(job["provider"], job["model"])
    fcs = [FileContentWithMimeType(file_path=f["path"], mime_type=f["mime"]) for f in job.get("files") or []]
    msg = UserMessage(text=job["text"], file_contents=fcs) if fcs else UserMessage(text=job["text"])
    reply = asyncio.run(chat.send_message(msg))
    if not isinstance(reply, str):
        reply = getattr(reply, "content", None) or str(reply)
    return {"ok": True, "reply": reply}


if __name__ == "__main__":
    import resource
    try:
        _job = json.loads(sys.stdin.read())
        _res = _run_job(_job)
    except Exception as e:  # noqa: BLE001 — reported to the parent as a clean error
        _res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    _res["peak_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
    sys.stdout.write(json.dumps(_res))
    sys.stdout.flush()
