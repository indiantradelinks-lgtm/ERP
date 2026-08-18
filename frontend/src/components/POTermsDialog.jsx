import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

export const TERMS_CAT_LABEL = {
  payment: "Payment Terms", advance: "Advance", tds: "TDS", delivery: "Delivery Terms",
  inclusions: "Inclusions", exclusions: "Exclusions", warranty: "Warranty",
  penalty: "Penalty / LD", general: "General Clauses",
};

export default function POTermsDialog({ po, onClose }) {
  const [templates, setTemplates] = useState([]);
  const [sel, setSel] = useState({});

  useEffect(() => {
    api.get("/procurement-extras/terms-templates").then((r) => {
      setTemplates(r.data || []);
      const existing = (po.terms_structured || []).map((t) => `${t.category}|${t.title}`);
      const init = {};
      (r.data || []).forEach((t) => {
        const k = `${t.category}|${t.title}`;
        if (existing.length ? existing.includes(k) : t.is_default) init[t.id] = true;
      });
      setSel(init);
    });
  }, [po]);

  const save = async () => {
    const chosen = templates.filter((t) => sel[t.id]).map((t) => ({ category: t.category, title: t.title, body: t.body }));
    try {
      await api.put(`/procurement-extras/pos/${po.id}/terms`, { terms_structured: chosen });
      toast.success("PO terms saved — will print on PO PDF & reflect on vendor bill entry");
      onClose(true);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  const cats = [...new Set(templates.map((t) => t.category))];
  return (
    <Dialog open onOpenChange={(o) => !o && onClose(false)}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="po-terms-dialog">
        <DialogHeader><DialogTitle>Terms & Conditions — {po.po_number}</DialogTitle></DialogHeader>
        {cats.map((c) => (
          <div key={c} className="mb-2">
            <div className="text-[10px] uppercase tracking-wider font-semibold text-slate-500 mb-1">{TERMS_CAT_LABEL[c] || c}</div>
            {templates.filter((t) => t.category === c).map((t) => (
              <label key={t.id} className="flex items-start gap-2 text-sm py-1 border-b border-slate-100 cursor-pointer">
                <input type="checkbox" className="mt-1" checked={!!sel[t.id]}
                  onChange={(e) => setSel({ ...sel, [t.id]: e.target.checked })}
                  data-testid={`po-term-chk-${t.id}`} />
                <span><b>{t.title}</b><span className="block text-xs text-slate-600">{t.body}</span></span>
              </label>
            ))}
          </div>
        ))}
        {templates.length === 0 && <div className="text-sm text-slate-400">No templates — create them in Procurement → PO Terms Master.</div>}
        <DialogFooter>
          <Button variant="outline" onClick={() => onClose(false)}>Cancel</Button>
          <Button onClick={save} data-testid="po-terms-save">Save Terms</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
