import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Pencil, Trash2, Plus } from "lucide-react";
import { toast } from "sonner";
import { api, apiErrorMessage } from "@/lib/api";

export default function TermsMasterDialog({ open, onOpenChange }) {
  const [rows, setRows] = useState([]);
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setRows((await api.get("/service-workflow/terms")).data); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  }, []);
  useEffect(() => { if (open) load(); }, [open, load]);

  const save = async () => {
    setBusy(true);
    try {
      if (editing.id) await api.put(`/service-workflow/terms/${editing.id}`, editing);
      else await api.post("/service-workflow/terms", editing);
      toast.success("Terms template saved");
      setEditing(null); load();
    } catch (e) { toast.error(apiErrorMessage(e)); } finally { setBusy(false); }
  };

  const remove = async (r) => {
    if (!window.confirm(`Delete "${r.title}"?`)) return;
    try { await api.delete(`/service-workflow/terms/${r.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(apiErrorMessage(e)); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto rounded-sm" data-testid="svc-terms-dialog">
        <DialogHeader><DialogTitle>Terms &amp; Conditions Master — Service POs</DialogTitle></DialogHeader>
        {!editing ? (
          <>
            <div className="flex justify-between items-center">
              <p className="text-xs text-muted-foreground">Templates appear in the T&amp;C dropdown while creating a Service PO and print on the PO PDF (one clause per line).</p>
              <Button size="sm" onClick={() => setEditing({ title: "", body: "", active: true })} data-testid="svc-terms-add"><Plus className="h-3.5 w-3.5 mr-1" /> Add</Button>
            </div>
            <div className="space-y-2">
              {rows.map((r) => (
                <div key={r.id} className="border rounded-md p-2 flex items-start justify-between gap-2" data-testid={`svc-terms-row-${r.id}`}>
                  <div className="min-w-0">
                    <div className="text-sm font-semibold flex items-center gap-2">{r.title}
                      {r.active === false && <Badge variant="outline" className="text-[9px]">inactive</Badge>}
                    </div>
                    <p className="text-xs text-muted-foreground whitespace-pre-wrap line-clamp-3">{r.body}</p>
                  </div>
                  <div className="shrink-0">
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setEditing({ ...r })} data-testid={`svc-terms-edit-${r.id}`}><Pencil className="h-3.5 w-3.5" /></Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => remove(r)} data-testid={`svc-terms-delete-${r.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>
                  </div>
                </div>
              ))}
              {!rows.length && <p className="text-sm text-muted-foreground text-center py-6">No templates yet — add your first Terms &amp; Conditions set</p>}
            </div>
          </>
        ) : (
          <div className="space-y-3">
            <div><Label className="text-xs">Title *</Label><Input value={editing.title} onChange={(e) => setEditing({ ...editing, title: e.target.value })} placeholder="e.g. Standard Service Terms" data-testid="svc-terms-title" /></div>
            <div><Label className="text-xs">Terms (one clause per line) *</Label><Textarea rows={8} value={editing.body} onChange={(e) => setEditing({ ...editing, body: e.target.value })} data-testid="svc-terms-body" /></div>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={editing.active !== false} onChange={(e) => setEditing({ ...editing, active: e.target.checked })} data-testid="svc-terms-active" /> Active (visible in PO dropdown)</label>
            <DialogFooter>
              <Button variant="outline" onClick={() => setEditing(null)}>Back</Button>
              <Button disabled={busy || !editing.title.trim() || !editing.body.trim()} onClick={save} data-testid="svc-terms-save">Save Template</Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
