import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { GitCompare } from "lucide-react";
import { api, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";

export default function VersionCompare({ approvalId, open, onClose }) {
  const [versions, setVersions] = useState([]);
  const [v1, setV1] = useState("");
  const [v2, setV2] = useState("");
  const [diff, setDiff] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || !approvalId) return;
    (async () => {
      try {
        const { data } = await api.get(`/approvals/${approvalId}/versions`);
        const sorted = (data || []).sort((a, b) => parseFloat(b.version) - parseFloat(a.version));
        setVersions(sorted);
        if (sorted.length >= 2) {
          setV1(sorted[1].version);
          setV2(sorted[0].version);
        } else if (sorted.length === 1) {
          setV1(sorted[0].version);
          setV2(sorted[0].version);
        }
      } catch (e) { toast.error(apiErrorMessage(e)); }
    })();
  }, [open, approvalId]);

  const runCompare = async () => {
    if (!v1 || !v2) return;
    setBusy(true);
    try {
      const { data } = await api.get(`/approvals/${approvalId}/versions/compare?v1=${v1}&v2=${v2}`);
      setDiff(data);
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setBusy(false); }
  };

  useEffect(() => { if (v1 && v2 && open) runCompare(); /* eslint-disable-line */ }, [v1, v2]);

  const render = (val) => {
    if (val === null || val === undefined) return <span className="text-muted-foreground italic">—</span>;
    if (typeof val === "object") return <code className="text-[10px] break-all">{JSON.stringify(val)}</code>;
    return String(val);
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl rounded-sm max-h-[90vh] overflow-y-auto" data-testid="version-compare-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <GitCompare className="h-5 w-5 text-blue-600" />
            Version Comparison
          </DialogTitle>
          <DialogDescription>
            Pick two versions to see the field-level differences (left = older, right = newer).
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center gap-3 mb-3">
          <select className="border rounded-sm p-1 text-sm" value={v1} onChange={(e) => setV1(e.target.value)} data-testid="version-v1">
            {versions.map((v) => <option key={v.version} value={v.version}>v{v.version} · {(v.saved_at || "").slice(0, 16)}</option>)}
          </select>
          <span className="text-muted-foreground">↔</span>
          <select className="border rounded-sm p-1 text-sm" value={v2} onChange={(e) => setV2(e.target.value)} data-testid="version-v2">
            {versions.map((v) => <option key={v.version} value={v.version}>v{v.version} · {(v.saved_at || "").slice(0, 16)}</option>)}
          </select>
          <Button size="sm" onClick={runCompare} disabled={busy} data-testid="version-compare-run">Compare</Button>
        </div>

        {diff && (
          <div className="border rounded-sm overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-slate-50">
                <tr>
                  <th className="p-2 text-left w-1/4">Field</th>
                  <th className="p-2 text-left w-1/3">v{diff.v1.version}</th>
                  <th className="p-2 text-left w-1/3">v{diff.v2.version}</th>
                </tr>
              </thead>
              <tbody>
                {diff.rows.map((r) => (
                  <tr key={r.key} className={r.changed ? "bg-amber-50" : ""} data-testid={`diff-row-${r.key}`}>
                    <td className="p-2 font-mono align-top">
                      {r.key}
                      {r.changed && <Badge className="ml-1 bg-amber-200 text-amber-900 text-[9px] py-0 px-1 h-4">Δ</Badge>}
                    </td>
                    <td className="p-2 align-top">{render(r.v1)}</td>
                    <td className="p-2 align-top">{render(r.v2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {diff?.history_diff && (
          <div className="grid grid-cols-2 gap-3 mt-3">
            <HistoryColumn title={`v${diff.v1.version} — last activity`} rows={diff.history_diff.v1_tail} />
            <HistoryColumn title={`v${diff.v2.version} — last activity`} rows={diff.history_diff.v2_tail} />
          </div>
        )}

        <DialogFooter><Button variant="ghost" onClick={onClose}>Close</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function HistoryColumn({ title, rows }) {
  return (
    <div className="border rounded-sm">
      <div className="p-2 bg-slate-50 text-[10px] uppercase tracking-wider font-bold">{title}</div>
      <ul className="divide-y text-xs">
        {(rows || []).length === 0 && <li className="p-2 text-muted-foreground">No activity</li>}
        {(rows || []).map((h, i) => (
          <li key={`${h.at}-${i}`} className="p-2">
            <div className="flex justify-between">
              <span className="font-semibold capitalize">{(h.action || "").replaceAll("_", " ")}</span>
              <span className="text-muted-foreground">{(h.at || "").slice(0, 16)}</span>
            </div>
            <div className="text-muted-foreground">{h.by} · {h.step_label}</div>
            {h.comment && <div className="italic mt-0.5">"{h.comment}"</div>}
          </li>
        ))}
      </ul>
    </div>
  );
}
