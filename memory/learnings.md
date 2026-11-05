- 2026-06 iter168: When repairing a corrupted JSX file via `head -N` truncation, previously applied search_replace edits in the truncated region can be silently lost. Always re-grep for the edited testids/markers afterwards.

## Iter 226 — memory
- `import emergentintegrations.llm.chat` loads litellm: +160 MB RSS, permanent. Never import it in the API
  process — use `ai_worker.llm_send(provider, model, system, text, files=[{path,mime}])` (child process).
- `/tmp` purge in `system_health.housekeeping` is age-based (mtime > N h); the container clock can jump
  after a pause, so test fixtures in /tmp may vanish — keep test artefacts elsewhere.
- Emergent object storage has no delete API: "migration" = verified OneDrive tier + OneDrive-first reads.
