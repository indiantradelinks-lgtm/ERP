import { useState } from "react";
import { Bookmark, BookmarkPlus, RotateCcw, Trash2, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

/** "Views" menu: apply / delete named presets, save current view, reset to default. */
export default function TableViewsMenu({ pagination, testidPrefix = "tbl" }) {
  const [saveOpen, setSaveOpen] = useState(false);
  const [name, setName] = useState("");
  const views = pagination?.views;
  if (!views) return null;
  const { presets, savePreset, applyPreset, deletePreset, resetView, isDefault, activePresetId } = views;

  const save = async () => {
    if (!name.trim()) return;
    await savePreset(name.trim());
    setName("");
    setSaveOpen(false);
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" className="h-9 rounded-sm" title="Saved views" data-testid={`${testidPrefix}-views-btn`}>
            <Bookmark className={`h-4 w-4 ${isDefault ? "" : "text-primary"}`} />
            {presets.length > 0 && <span className="ml-1 text-[10px] font-bold tabular-nums">{presets.length}</span>}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64 rounded-sm" data-testid={`${testidPrefix}-views-menu`}>
          <DropdownMenuLabel className="text-[10px] uppercase tracking-wider text-muted-foreground">My saved views</DropdownMenuLabel>
          {presets.length === 0 && <div className="px-2 py-1.5 text-xs text-muted-foreground">No saved views yet.</div>}
          {presets.map((p) => (
            <DropdownMenuItem key={p.id} className="flex items-center gap-2 text-sm" onSelect={() => applyPreset(p)} data-testid={`${testidPrefix}-view-${p.id}`}>
              <Check className={`h-3.5 w-3.5 ${activePresetId === p.id ? "text-primary" : "opacity-0"}`} />
              <span className="flex-1 truncate">{p.name}</span>
              <button
                type="button"
                className="text-muted-foreground hover:text-destructive"
                onClick={(e) => { e.stopPropagation(); e.preventDefault(); deletePreset(p.id); }}
                title="Delete view"
                data-testid={`${testidPrefix}-view-delete-${p.id}`}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => setSaveOpen(true)} className="text-sm" data-testid={`${testidPrefix}-view-save`}>
            <BookmarkPlus className="h-4 w-4 mr-2 text-primary" /> Save current view…
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={resetView} disabled={isDefault} className="text-sm" data-testid={`${testidPrefix}-view-reset`}>
            <RotateCcw className="h-4 w-4 mr-2" /> Reset to default
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={saveOpen} onOpenChange={setSaveOpen}>
        <DialogContent className="max-w-sm rounded-sm" data-testid={`${testidPrefix}-view-save-dialog`}>
          <DialogHeader>
            <DialogTitle className="font-display">Save current view</DialogTitle>
            <DialogDescription className="text-xs">Remembers this table's search, sort and rows-per-page under a name you choose.</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5 py-1">
            <Label className="text-xs uppercase tracking-wider">View name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Pending this month" className="h-9 rounded-sm"
              onKeyDown={(e) => e.key === "Enter" && save()} data-testid={`${testidPrefix}-view-name`} autoFocus />
          </div>
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setSaveOpen(false)}>Cancel</Button>
            <Button className="rounded-sm" onClick={save} disabled={!name.trim()} data-testid={`${testidPrefix}-view-save-confirm`}>Save view</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
