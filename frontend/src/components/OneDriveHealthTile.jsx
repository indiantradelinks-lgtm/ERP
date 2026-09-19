import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { Cloud, CloudOff, AlertTriangle, CheckCircle2, RefreshCcw, Loader2 } from "lucide-react";
import { fmtDT } from "@/lib/datetime";
import { toast } from "sonner";

const TONE = {
  disabled: "border-slate-200 bg-slate-50 text-slate-600",
  failing: "border-rose-200 bg-rose-50 text-rose-700",
  config: "border-rose-200 bg-rose-50 text-rose-700",
  retrying: "border-amber-200 bg-amber-50 text-amber-800",
  syncing: "border-sky-200 bg-sky-50 text-sky-800",
  healthy: "border-emerald-200 bg-emerald-50 text-emerald-700",
};
const LABEL = {
  disabled: "Disabled", failing: "Needs Attention", config: "Check Connection", retrying: "Retrying",
  syncing: "Syncing", healthy: "Healthy",
};
const ICON = {
  disabled: CloudOff, failing: AlertTriangle, config: AlertTriangle, retrying: RefreshCcw,
  syncing: Loader2, healthy: CheckCircle2,
};

export const OneDriveHealthTile = () => {
  const [h, setH] = useState(null);
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();

  const load = useCallback(() => {
    api.get("/admin/onedrive/health").then((r) => setH(r.data)).catch(() => setH(null));
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [load]);

  if (!h) return null;

  const state = h.status || (!h.enabled ? "disabled" : h.failed ? "failing" : "healthy");
  const Icon = ICON[state] || Cloud;

  const retry = async (e) => {
    e.stopPropagation();
    setBusy(true);
    try {
      const { data } = await api.post("/admin/onedrive/retry-failed");
      await api.post("/admin/onedrive/process-now").catch(() => {});
      toast.success(`${data.requeued ?? 0} document(s) re-queued for sync`);
      setTimeout(load, 2500);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not re-queue the failed documents");
    } finally { setBusy(false); }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => nav("/app/admin/onedrive")}
      onKeyDown={(e) => e.key === "Enter" && nav("/app/admin/onedrive")}
      className={`w-full text-left border rounded-md p-4 transition-colors hover:opacity-90 cursor-pointer ${TONE[state] || TONE.healthy}`}
      data-testid="onedrive-health-tile"
    >
      <div className="flex items-center justify-between mb-2 gap-2">
        <div className="flex items-center gap-2 font-semibold text-sm">
          <Cloud className="h-4 w-4" /> OneDrive Document Sync
        </div>
        <div className="flex items-center gap-2">
          {(state === "failing" || state === "config") && (
            <button onClick={retry} disabled={busy}
              className="text-[11px] font-medium border border-current/30 rounded px-2 py-0.5 hover:bg-white/50"
              data-testid="onedrive-health-retry">
              {busy ? "Re-queuing…" : "Retry now"}
            </button>
          )}
          <span className="flex items-center gap-1 text-xs font-medium" data-testid="onedrive-health-status">
            <Icon className={`h-3.5 w-3.5 ${state === "syncing" ? "animate-spin" : ""}`} /> {LABEL[state]}
          </span>
        </div>
      </div>
      <div className="grid grid-cols-4 gap-2 text-center">
        <div><div className="text-lg font-bold" data-testid="onedrive-health-pushed">{h.pushed}</div><div className="text-[10px] uppercase tracking-wider opacity-70">Pushed</div></div>
        <div><div className="text-lg font-bold" data-testid="onedrive-health-pending">{h.pending}</div><div className="text-[10px] uppercase tracking-wider opacity-70">Pending{h.retrying ? ` · ${h.retrying} retrying` : ""}</div></div>
        <div><div className="text-lg font-bold" data-testid="onedrive-health-failed">{h.failed}</div><div className="text-[10px] uppercase tracking-wider opacity-70">Needs Attention</div></div>
        <div><div className="text-lg font-bold" data-testid="onedrive-health-total">{h.files_total}</div><div className="text-[10px] uppercase tracking-wider opacity-70">Docs Total</div></div>
      </div>
      {(state === "failing" || state === "config") && h.last_error && (
        <div className="mt-2 text-[11px] font-mono truncate opacity-80" title={h.last_error}>
          {h.last_error}
        </div>
      )}
      <div className="mt-1 flex flex-wrap gap-x-3 text-[10px] opacity-70">
        {h.last_pushed_at && <span>Last successful push: {fmtDT(h.last_pushed_at)}</span>}
        <span>Documents are stored in the ERP first — OneDrive is a mirror, so a sync delay never affects what you see here.</span>
      </div>
    </div>
  );
};

export default OneDriveHealthTile;
