import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { Cloud, CloudOff, AlertTriangle, CheckCircle2 } from "lucide-react";
import { fmtDT } from "@/lib/datetime";

export const OneDriveHealthTile = () => {
  const [h, setH] = useState(null);
  const nav = useNavigate();

  useEffect(() => {
    api.get("/admin/onedrive/health").then((r) => setH(r.data)).catch(() => setH(null));
  }, []);

  if (!h) return null;
  const failing = h.failed > 0 || (h.enabled && h.last_test_ok === false);
  const status = !h.enabled ? "Disabled" : failing ? "Sync Failing" : "Healthy";
  const tone = !h.enabled
    ? "border-slate-200 bg-slate-50 text-slate-600"
    : failing
      ? "border-rose-200 bg-rose-50 text-rose-700"
      : "border-emerald-200 bg-emerald-50 text-emerald-700";
  const Icon = !h.enabled ? CloudOff : failing ? AlertTriangle : CheckCircle2;

  return (
    <button
      onClick={() => nav("/app/admin/onedrive")}
      className={`w-full text-left border rounded-md p-4 transition-colors hover:opacity-90 ${tone}`}
      data-testid="onedrive-health-tile"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 font-semibold text-sm">
          <Cloud className="h-4 w-4" /> OneDrive Document Sync
        </div>
        <span className="flex items-center gap-1 text-xs font-medium" data-testid="onedrive-health-status">
          <Icon className="h-3.5 w-3.5" /> {status}
        </span>
      </div>
      <div className="grid grid-cols-4 gap-2 text-center">
        <div><div className="text-lg font-bold" data-testid="onedrive-health-pushed">{h.pushed}</div><div className="text-[10px] uppercase tracking-wider opacity-70">Pushed</div></div>
        <div><div className="text-lg font-bold" data-testid="onedrive-health-pending">{h.pending}</div><div className="text-[10px] uppercase tracking-wider opacity-70">Pending</div></div>
        <div><div className="text-lg font-bold" data-testid="onedrive-health-failed">{h.failed}</div><div className="text-[10px] uppercase tracking-wider opacity-70">Failed</div></div>
        <div><div className="text-lg font-bold" data-testid="onedrive-health-total">{h.files_total}</div><div className="text-[10px] uppercase tracking-wider opacity-70">Docs Total</div></div>
      </div>
      {failing && h.last_error && (
        <div className="mt-2 text-[11px] font-mono truncate opacity-80" title={h.last_error}>
          {h.last_error}
        </div>
      )}
      {h.last_pushed_at && (
        <div className="mt-1 text-[10px] opacity-60">Last successful push: {fmtDT(h.last_pushed_at)}</div>
      )}
    </button>
  );
};

export default OneDriveHealthTile;
