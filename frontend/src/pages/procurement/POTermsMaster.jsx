import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Plus, Pencil, Trash2, ListChecks } from "lucide-react";
import { TERMS_CAT_LABEL } from "@/components/POTermsDialog";

const CATS = Object.keys(TERMS_CAT_LABEL);
const blank = () => ({ category: "payment", title: "", body: "", is_default: false, sort_order: 99 });

export default function POTermsMaster() {
  const [rows, setRows] = useState([]);
  const [edit, setEdit] = useState(null);

  const load = () => api.get("/procurement-extras/terms-templates").then((r) => setRows(r.data || []));
  useEffect(() => { load(); }, []);

  const save = async () => {
    if (!edit.title || !edit.body) { toast.error("Title and clause text required"); return; }
    try {
      if (edit.id) await api.put(`/procurement-extras/terms-templates/${edit.id}`, edit);
      else await api.post("/procurement-extras/terms-templates", edit);
      toast.success("Saved");
      setEdit(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const remove = async (t) => {
    if (!window.confirm(`Delete "${t.title}"?`)) return;
    try { await api.delete(`/procurement-extras/terms-templates/${t.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  return (
    <div className="p-4 space-y-4" data-testid="po-terms-master">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <ListChecks className="h-4 w-4" /> PO Terms & Conditions Master
            <span className="text-sm text-slate-500 font-normal">predefined clauses applied to POs & fetched into vendor bills</span>
          </CardTitle>
          <Button size="sm" onClick={() => setEdit(blank())} data-testid="terms-new-btn"><Plus className="h-4 w-4 mr-1" />New Clause</Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {CATS.filter((c) => rows.some((r) => r.category === c)).map((c) => (
            <div key={c}>
              <div className="text-[10px] uppercase tracking-wider font-semibold text-slate-500 mb-1">{TERMS_CAT_LABEL[c]}</div>
              <div className="border rounded-md divide-y">
                {rows.filter((r) => r.category === c).map((t) => (
                  <div key={t.id} className="flex items-start justify-between gap-3 px-3 py-2" data-testid={`terms-row-${t.id}`}>
                    <div>
                      <div className="text-sm font-semibold flex items-center gap-2">
                        {t.title}
                        {t.is_default && <Badge className="bg-emerald-100 text-emerald-700 text-[10px]">default on new PO</Badge>}
                      </div>
                      <div className="text-xs text-slate-600">{t.body}</div>
                    </div>
                    <div className="flex gap-1 shrink-0">
                      <Button size="sm" variant="ghost" onClick={() => setEdit({ ...t })} data-testid={`terms-edit-${t.id}`}><Pencil className="h-3.5 w-3.5" /></Button>
                      <Button size="sm" variant="ghost" className="text-rose-600" onClick={() => remove(t)} data-testid={`terms-del-${t.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
          {rows.length === 0 && <div className="text-sm text-slate-400 py-6 text-center">Loading templates…</div>}
        </CardContent>
      </Card>

      {edit && (
        <Dialog open onOpenChange={(o) => !o && setEdit(null)}>
          <DialogContent className="max-w-lg" data-testid="terms-edit-dialog">
            <DialogHeader><DialogTitle>{edit.id ? "Edit Clause" : "New Clause"}</DialogTitle></DialogHeader>
            <div className="space-y-3">
              <div>
                <label className="text-[10px] uppercase tracking-wider text-slate-500">Category</label>
                <select className="h-9 w-full rounded-sm border bg-background px-2" value={edit.category}
                  onChange={(e) => setEdit({ ...edit, category: e.target.value })} data-testid="terms-cat">
                  {CATS.map((c) => <option key={c} value={c}>{TERMS_CAT_LABEL[c]}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider text-slate-500">Title</label>
                <Input value={edit.title} onChange={(e) => setEdit({ ...edit, title: e.target.value })} data-testid="terms-title" />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider text-slate-500">Clause Text</label>
                <Textarea rows={4} value={edit.body} onChange={(e) => setEdit({ ...edit, body: e.target.value })} data-testid="terms-body" />
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={!!edit.is_default} onChange={(e) => setEdit({ ...edit, is_default: e.target.checked })} data-testid="terms-default" />
                Pre-select by default on new POs
              </label>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setEdit(null)}>Cancel</Button>
              <Button onClick={save} data-testid="terms-save">Save</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
