import { useState } from "react";
import { useLocation } from "react-router-dom";
import { HelpCircle, Pencil, RotateCcw, ListOrdered, Lightbulb } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { toast } from "sonner";

export default function PageHelp() {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [guide, setGuide] = useState(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get("/help/guide", { params: { path: location.pathname } });
      setGuide(data);
    } catch { setGuide(null); }
  };

  const onOpen = (v) => {
    setOpen(v);
    setEditing(false);
    if (v) load();
  };

  const startEdit = () => {
    setDraft({ title: guide.title || "", description: guide.description || "",
      steps: (guide.steps || []).join("\n"), tips: (guide.tips || []).join("\n") });
    setEditing(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.put("/help/guide", {
        path: guide.path || location.pathname, title: draft.title, description: draft.description,
        steps: draft.steps.split("\n"), tips: draft.tips.split("\n"),
      });
      setGuide(data); setEditing(false); toast.success("Guide saved");
    } catch (e) { toast.error(e?.response?.data?.detail || "Save failed"); }
    finally { setSaving(false); }
  };

  const reset = async () => {
    if (!window.confirm("Reset this guide to the built-in text?")) return;
    try { await api.delete("/help/guide", { params: { path: guide.path } }); toast.success("Reset to built-in"); load(); setEditing(false); }
    catch { toast.error("Reset failed"); }
  };

  return (
    <>
      <Button variant="ghost" size="icon" className="h-9 w-9 text-muted-foreground hover:text-primary"
        onClick={() => onOpen(true)} title="How this page works" data-testid="page-help-btn">
        <HelpCircle className="h-5 w-5" />
      </Button>
      <Sheet open={open} onOpenChange={onOpen}>
        <SheetContent side="right" className="w-full sm:max-w-md overflow-y-auto" data-testid="page-help-panel">
          {guide && !editing && (
            <>
              <SheetHeader>
                <SheetTitle className="flex items-center gap-2 text-left">
                  <HelpCircle className="h-5 w-5 text-primary shrink-0" /> {guide.title}
                </SheetTitle>
                <SheetDescription className="text-left">{guide.description}</SheetDescription>
              </SheetHeader>
              {guide.steps?.length > 0 && (
                <div className="mt-5">
                  <div className="text-[10px] font-bold uppercase tracking-[0.15em] text-primary mb-2 flex items-center gap-1.5">
                    <ListOrdered className="h-3.5 w-3.5" /> How it works — step by step
                  </div>
                  <ol className="space-y-2" data-testid="help-steps">
                    {guide.steps.map((s, i) => (
                      <li key={i} className="flex gap-2.5 text-sm">
                        <span className="shrink-0 h-5 w-5 rounded-full bg-primary/10 text-primary text-[11px] font-bold flex items-center justify-center mt-0.5">{i + 1}</span>
                        <span>{s}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
              {guide.tips?.length > 0 && (
                <div className="mt-5 border border-amber-200 bg-amber-50/70 rounded-sm p-3">
                  <div className="text-[10px] font-bold uppercase tracking-[0.15em] text-amber-800 mb-1.5 flex items-center gap-1.5">
                    <Lightbulb className="h-3.5 w-3.5" /> Tips
                  </div>
                  <ul className="space-y-1 text-sm text-amber-900 list-disc pl-4" data-testid="help-tips">
                    {guide.tips.map((t, i) => <li key={i}>{t}</li>)}
                  </ul>
                </div>
              )}
              <div className="mt-6 flex items-center gap-2">
                {guide.source === "custom" && <Badge variant="outline" className="text-[10px]">Customised</Badge>}
                {guide.can_edit && (
                  <div className="ml-auto flex gap-2">
                    {guide.source === "custom" && (
                      <Button variant="outline" size="sm" onClick={reset} data-testid="help-reset-btn"><RotateCcw className="h-3.5 w-3.5 mr-1" /> Reset</Button>
                    )}
                    <Button variant="outline" size="sm" onClick={startEdit} data-testid="help-edit-btn"><Pencil className="h-3.5 w-3.5 mr-1" /> Edit Guide</Button>
                  </div>
                )}
              </div>
            </>
          )}
          {guide && editing && (
            <>
              <SheetHeader>
                <SheetTitle className="text-left">Edit Page Guide</SheetTitle>
                <SheetDescription className="text-left">{guide.path} — one step/tip per line.</SheetDescription>
              </SheetHeader>
              <div className="mt-4 space-y-3">
                <div><Label className="text-xs">Title</Label>
                  <Input className="h-9 mt-1" value={draft.title} onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))} data-testid="help-edit-title" /></div>
                <div><Label className="text-xs">Description</Label>
                  <Textarea rows={2} value={draft.description} onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))} data-testid="help-edit-desc" /></div>
                <div><Label className="text-xs">Steps (one per line)</Label>
                  <Textarea rows={8} value={draft.steps} onChange={(e) => setDraft((d) => ({ ...d, steps: e.target.value }))} data-testid="help-edit-steps" /></div>
                <div><Label className="text-xs">Tips (one per line)</Label>
                  <Textarea rows={3} value={draft.tips} onChange={(e) => setDraft((d) => ({ ...d, tips: e.target.value }))} data-testid="help-edit-tips" /></div>
                <div className="flex justify-end gap-2">
                  <Button variant="outline" size="sm" onClick={() => setEditing(false)}>Cancel</Button>
                  <Button size="sm" onClick={save} disabled={saving} data-testid="help-save-btn">{saving ? "Saving…" : "Save Guide"}</Button>
                </div>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </>
  );
}
