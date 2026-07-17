/**
 * Resource Plan bulk tools:
 *  - BulkUploadDialog: per-tab Excel template download + upload into project_resources
 *  - QuickQtyDialog: full item master + designations with qty-only entry; 0 qty auto-skipped;
 *    result goes to Plan or straight to draft Resource Requests.
 */
import { useMemo, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Download, Upload, Search, Users, Package } from "lucide-react";

export function BulkUploadDialog({ projectId, type, onClose, onSaved }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const downloadTemplate = async () => {
    try {
      const r = await api.get("/resource-plan/template", { params: { type }, responseType: "blob" });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `resource_plan_${type}_template.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Template download failed"); }
  };

  const upload = async () => {
    if (!file) { toast.error("Choose an .xlsx file first"); return; }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await api.post(`/resource-plan/upload/${projectId}?type=${type}`, fd,
        { headers: { "Content-Type": "multipart/form-data" } });
      setResult(r.data);
      if (r.data.created > 0) toast.success(`Added ${r.data.created} ${type} plan line${r.data.created > 1 ? "s" : ""}`);
      else toast.error("No rows added — check the errors below");
    } catch (e) { toast.error(e.response?.data?.detail || "Upload failed"); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Bulk Upload — {type[0].toUpperCase() + type.slice(1)} Plan</DialogTitle>
          <DialogDescription>Rows with quantity/count 0 or blank are skipped automatically.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <Button variant="outline" onClick={downloadTemplate} data-testid="rpb-download-template">
            <Download className="h-4 w-4 mr-1" /> Download {type} template (.xlsx)
          </Button>
          <div>
            <Label className="text-[10px] uppercase tracking-wider">Filled template</Label>
            <Input type="file" accept=".xlsx" className="mt-1" onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid="rpb-file-input" />
          </div>
          {result && (
            <div className="border rounded-sm p-3 text-sm bg-slate-50 space-y-1" data-testid="rpb-result">
              <div>✓ Created: <b>{result.created}</b> · Skipped (0 qty): {result.skipped_zero} · Errors: {result.errors?.length || 0}</div>
              {(result.errors || []).slice(0, 8).map((e, i) => (
                <div key={i} className="text-xs text-red-600">Row {e.row}: {e.error}</div>
              ))}
              {(result.errors || []).length > 8 && <div className="text-xs text-slate-500">…and {result.errors.length - 8} more</div>}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => (result?.created ? onSaved() : onClose())}>{result?.created ? "Done" : "Close"}</Button>
          <Button onClick={upload} disabled={busy || !file} data-testid="rpb-upload-btn">
            <Upload className="h-4 w-4 mr-1" /> {busy ? "Uploading…" : "Upload"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function QuickQtyDialog({ projectId, items, designations, onClose, onSaved }) {
  const [tab, setTab] = useState("items");
  const [q, setQ] = useState("");
  const [qtys, setQtys] = useState({});
  const [mode, setMode] = useState("plan");
  const [busy, setBusy] = useState(false);

  const setQty = (key, v) => setQtys((m) => ({ ...m, [key]: v }));
  const nonZero = Object.entries(qtys).filter(([, v]) => Number(v) > 0);

  const grouped = useMemo(() => {
    const s = q.toLowerCase();
    const filtered = items.filter((i) => !s || (i.name || "").toLowerCase().includes(s) || (i.code || "").toLowerCase().includes(s) || (i.category_name || "").toLowerCase().includes(s));
    const m = {};
    for (const it of filtered) { const k = it.category_name || "Uncategorised"; (m[k] = m[k] || []).push(it); }
    return Object.entries(m).sort(([a], [b]) => a.localeCompare(b));
  }, [items, q]);

  const filteredDesigs = useMemo(() => {
    const s = q.toLowerCase();
    return designations.filter((d) => !s || (d.name || "").toLowerCase().includes(s) || (d.code || "").toLowerCase().includes(s));
  }, [designations, q]);

  const save = async () => {
    if (nonZero.length === 0) { toast.error("Enter a quantity for at least one row"); return; }
    setBusy(true);
    try {
      const lines = nonZero.map(([key, v]) => {
        const [kind, id] = key.split("::");
        return { kind, ref_id: id, quantity: Number(v) };
      });
      const r = await api.post(`/resource-plan/quick-fill/${projectId}`, { mode, lines });
      const d = r.data;
      toast.success(mode === "plan"
        ? `Added ${d.created} plan line${d.created > 1 ? "s" : ""} (${d.skipped_zero} zero-qty skipped)`
        : `Raised ${d.created} draft request${d.created > 1 ? "s" : ""} — submit them from Resource Requests`);
      onSaved();
    } catch (e) { toast.error(e.response?.data?.detail || "Save failed"); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[92vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Quick Quantity Entry</DialogTitle>
          <DialogDescription>Type quantities against the complete list — rows left at 0 are eliminated automatically.</DialogDescription>
        </DialogHeader>
        <div className="flex items-center gap-2">
          <div className="flex border rounded-sm overflow-hidden text-sm">
            <button className={`px-3 py-1.5 flex items-center gap-1 ${tab === "items" ? "bg-primary text-primary-foreground" : "bg-background"}`} onClick={() => setTab("items")} data-testid="qq-tab-items">
              <Package className="h-3.5 w-3.5" /> Items
            </button>
            <button className={`px-3 py-1.5 flex items-center gap-1 ${tab === "manpower" ? "bg-primary text-primary-foreground" : "bg-background"}`} onClick={() => setTab("manpower")} data-testid="qq-tab-manpower">
              <Users className="h-3.5 w-3.5" /> Manpower
            </button>
          </div>
          <div className="relative flex-1">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-slate-400" />
            <Input placeholder="Search item / code / category / designation…" value={q} onChange={(e) => setQ(e.target.value)} className="pl-8 h-9" data-testid="qq-search" />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto border rounded-sm min-h-[300px]" data-testid="qq-list">
          {tab === "items" ? (
            grouped.length === 0 ? <div className="text-center py-10 text-slate-400 text-sm">No items match.</div> :
            grouped.map(([cat, rows]) => (
              <div key={cat}>
                <div className="sticky top-0 bg-slate-100 px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-slate-600 border-b">{cat} ({rows.length})</div>
                {rows.map((it) => {
                  const key = `item::${it.id}`;
                  return (
                    <div key={it.id} className="flex items-center gap-2 px-3 py-1 border-b hover:bg-slate-50 text-sm">
                      <span className="font-mono text-[10px] text-primary w-24 shrink-0">{it.code}</span>
                      <span className="flex-1 truncate">{it.name}</span>
                      <span className="text-xs text-slate-500 w-12">{it.unit || "Nos"}</span>
                      <Input type="number" min="0" value={qtys[key] ?? ""} placeholder="0"
                             onChange={(e) => setQty(key, e.target.value)}
                             className={`h-7 w-24 text-right ${Number(qtys[key]) > 0 ? "border-green-500 bg-green-50" : ""}`}
                             data-testid={`qq-qty-${it.id}`} />
                    </div>
                  );
                })}
              </div>
            ))
          ) : (
            filteredDesigs.length === 0 ? <div className="text-center py-10 text-slate-400 text-sm">No designations match.</div> :
            filteredDesigs.map((d) => {
              const key = `manpower::${d.id}`;
              return (
                <div key={d.id} className="flex items-center gap-2 px-3 py-1 border-b hover:bg-slate-50 text-sm">
                  <span className="font-mono text-[10px] text-primary w-24 shrink-0">{d.code}</span>
                  <span className="flex-1 truncate">{d.name}</span>
                  <span className="text-xs text-slate-500 w-12">Persons</span>
                  <Input type="number" min="0" value={qtys[key] ?? ""} placeholder="0"
                         onChange={(e) => setQty(key, e.target.value)}
                         className={`h-7 w-24 text-right ${Number(qtys[key]) > 0 ? "border-green-500 bg-green-50" : ""}`}
                         data-testid={`qq-qty-${d.id}`} />
                </div>
              );
            })
          )}
        </div>

        <DialogFooter className="flex items-center sm:justify-between gap-3">
          <div className="flex items-center gap-4 text-sm">
            <span className="font-semibold text-green-700" data-testid="qq-count">{nonZero.length} selected</span>
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input type="radio" checked={mode === "plan"} onChange={() => setMode("plan")} data-testid="qq-mode-plan" /> Add to Plan
            </label>
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input type="radio" checked={mode === "request"} onChange={() => setMode("request")} data-testid="qq-mode-request" /> Raise Requests (drafts)
            </label>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose}>Cancel</Button>
            <Button onClick={save} disabled={busy || nonZero.length === 0} data-testid="qq-save">
              {busy ? "Saving…" : `Add ${nonZero.length} line${nonZero.length === 1 ? "" : "s"}`}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
