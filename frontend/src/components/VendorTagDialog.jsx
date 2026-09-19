import { useEffect, useMemo, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";
import { Loader2, Tags, Search } from "lucide-react";
import { lookupGet } from "@/lib/lookups";

export const VendorTagDialog = ({ onClose }) => {
  const [vendors, setVendors] = useState(null);
  const [cats, setCats] = useState([]);
  const [dirty, setDirty] = useState({});          // vendor_id -> categories[]
  const [onlyUntagged, setOnlyUntagged] = useState(true);
  const [query, setQuery] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([lookupGet("/vendors"), api.get("/vendor-categories")])
      .then(([v, c]) => { setVendors(v.data || []); setCats(c.data || []); })
      .catch((e) => toast.error(apiErrorMessage(e, "Failed to load vendors")));
  }, []);

  const rows = useMemo(() => {
    if (!vendors) return [];
    let list = vendors;
    if (onlyUntagged) list = list.filter((v) => !(v.categories || []).length || dirty[v.id] !== undefined);
    if (query.trim()) {
      const q = query.toLowerCase();
      list = list.filter((v) => String(v.name || "").toLowerCase().includes(q));
    }
    return list;
  }, [vendors, onlyUntagged, query, dirty]);

  const current = (v) => dirty[v.id] ?? v.categories ?? [];
  const toggle = (v, code) => {
    const cur = current(v);
    setDirty((d) => ({ ...d, [v.id]: cur.includes(code) ? cur.filter((c) => c !== code) : [...cur, code] }));
  };

  const dirtyIds = Object.keys(dirty).filter((id) => {
    const v = vendors?.find((x) => x.id === id);
    return v && JSON.stringify([...(dirty[id] || [])].sort()) !== JSON.stringify([...(v.categories || [])].sort());
  });

  const saveAll = async () => {
    setSaving(true);
    let ok = 0;
    for (const id of dirtyIds) {
      try {
        await api.put(`/vendors/${id}`, { categories: dirty[id] });
        ok += 1;
      } catch (e) {
        toast.error(apiErrorMessage(e, `Failed to save ${vendors.find((v) => v.id === id)?.name || id}`));
      }
    }
    setSaving(false);
    if (ok) toast.success(`Tagged ${ok} vendor(s)`);
    onClose(ok > 0);
  };

  const untaggedCount = (vendors || []).filter((v) => !(v.categories || []).length).length;

  return (
    <Dialog open onOpenChange={(o) => !o && onClose(false)}>
      <DialogContent className="max-w-3xl rounded-sm max-h-[85vh] overflow-y-auto" data-testid="vendor-tag-dialog">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2"><Tags className="h-4 w-4" /> Quick Vendor Category Tagging</DialogTitle>
          <DialogDescription>Tag vendors with the categories they supply — RFQ vendor filtering uses these tags. {untaggedCount} vendor(s) currently untagged.</DialogDescription>
        </DialogHeader>
        <div className="flex items-center gap-3">
          <div className="relative w-64">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input className="pl-8 h-8 rounded-sm text-sm" placeholder="Search vendor…" value={query} onChange={(e) => setQuery(e.target.value)} data-testid="vendor-tag-search" />
          </div>
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
            <input type="checkbox" checked={onlyUntagged} onChange={(e) => setOnlyUntagged(e.target.checked)} data-testid="vendor-tag-untagged-only" /> Untagged only
          </label>
        </div>
        {!vendors && <div className="text-sm text-muted-foreground py-6 text-center">Loading…</div>}
        {vendors && rows.length === 0 && <div className="text-sm text-muted-foreground py-6 text-center" data-testid="vendor-tag-empty">No {onlyUntagged ? "untagged " : ""}vendors{query ? " matching search" : ""}. 🎉</div>}
        <div className="divide-y divide-border border rounded-sm">
          {rows.map((v) => (
            <div key={v.id} className="p-2.5" data-testid={`vendor-tag-row-${v.id}`}>
              <div className="text-sm font-semibold mb-1.5">{v.name} {dirtyIds.includes(v.id) && <span className="text-[9px] uppercase bg-amber-100 text-amber-800 px-1 py-0.5 rounded-sm align-middle">unsaved</span>}</div>
              <div className="flex flex-wrap gap-1">
                {cats.map((c) => {
                  const active = current(v).includes(c.code);
                  return (
                    <button key={c.code} type="button" onClick={() => toggle(v, c.code)}
                      className={`text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded-sm border transition-colors ${active ? "bg-primary text-primary-foreground border-primary" : "border-border text-muted-foreground hover:border-primary/40"}`}
                      data-testid={`vendor-tag-${v.id}-${c.code}`} title={c.name}>
                      {c.name}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={() => onClose(false)} data-testid="vendor-tag-close">Close</Button>
          <Button className="rounded-sm" onClick={saveAll} disabled={saving || dirtyIds.length === 0} data-testid="vendor-tag-save">
            {saving && <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />} Save {dirtyIds.length ? `${dirtyIds.length} vendor(s)` : "Changes"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default VendorTagDialog;
