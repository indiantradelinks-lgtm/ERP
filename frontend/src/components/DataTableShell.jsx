import { useState, useMemo } from "react";
import { Plus, Search, Trash2, Pencil, FileSpreadsheet, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { downloadExport } from "@/lib/exports";

/**
 * Generic data table with create/edit/delete dialog.
 * columns: [{ key, label, render?, badge?: (row) => ({text, tone}) }]
 * fields: [{ key, label, type?: 'text'|'number'|'select'|'textarea', options?: [] }]
 */
export default function DataTableShell({
  title,
  description,
  data,
  columns,
  fields,
  onCreate,
  onUpdate,
  onDelete,
  testidPrefix = "tbl",
  searchKeys,
  rightSlot,
  exportResource,
  canWrite = false,
  canDelete = false,
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({});

  const filtered = useMemo(() => {
    if (!query) return data;
    const q = query.toLowerCase();
    const keys = searchKeys || columns.map((c) => c.key);
    return data.filter((row) => keys.some((k) => String(row?.[k] ?? "").toLowerCase().includes(q)));
  }, [data, query, columns, searchKeys]);

  const startCreate = () => {
    setEditing(null);
    setForm({});
    setOpen(true);
  };
  const startEdit = (row) => {
    setEditing(row);
    setForm({ ...row });
    setOpen(true);
  };

  const save = async () => {
    const payload = { ...form };
    // coerce numbers
    fields.forEach((f) => {
      if (f.type === "number" && payload[f.key] !== undefined && payload[f.key] !== "") {
        payload[f.key] = Number(payload[f.key]);
      }
    });
    if (editing) await onUpdate(editing.id, payload);
    else await onCreate(payload);
    setOpen(false);
  };

  return (
    <div className="bg-card border border-border rounded-sm">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 p-4 border-b border-border">
        <div>
          <h2 className="font-display text-xl font-bold tracking-tight">{title}</h2>
          {description && <p className="text-xs text-muted-foreground mt-0.5">{description}</p>}
        </div>
        <div className="flex items-center gap-2 w-full md:w-auto">
          <div className="relative flex-1 md:w-72">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search…"
              className="pl-9 h-9 rounded-sm"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              data-testid={`${testidPrefix}-search`}
            />
          </div>
          {rightSlot}
          {exportResource && (
            <>
              <Button variant="outline" className="h-9 rounded-sm" onClick={() => downloadExport(exportResource, "xlsx")} data-testid={`${testidPrefix}-export-xlsx`} title="Export Excel">
                <FileSpreadsheet className="h-4 w-4" />
              </Button>
              <Button variant="outline" className="h-9 rounded-sm" onClick={() => downloadExport(exportResource, "pdf")} data-testid={`${testidPrefix}-export-pdf`} title="Export PDF">
                <FileText className="h-4 w-4" />
              </Button>
            </>
          )}
          {onCreate && canWrite && (
            <Dialog open={open} onOpenChange={setOpen}>
              <DialogTrigger asChild>
                <Button className="h-9 rounded-sm" onClick={startCreate} data-testid={`${testidPrefix}-add-btn`}>
                  <Plus className="h-4 w-4 mr-1" /> New
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-xl rounded-sm">
                <DialogHeader>
                  <DialogTitle className="font-display">{editing ? `Edit ${title}` : `New ${title}`}</DialogTitle>
                </DialogHeader>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 py-2">
                  {fields.map((f) => (
                    <div key={f.key} className={cn("flex flex-col gap-1.5", f.full && "md:col-span-2")}>
                      <Label className="text-xs uppercase tracking-wider">{f.label}</Label>
                      {f.type === "textarea" ? (
                        <textarea
                          className="w-full min-h-[80px] rounded-sm border border-input bg-background p-2 text-sm"
                          value={form[f.key] ?? ""}
                          onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                          data-testid={`${testidPrefix}-field-${f.key}`}
                        />
                      ) : f.type === "select" ? (
                        <select
                          className="h-9 rounded-sm border border-input bg-background px-2 text-sm"
                          value={form[f.key] ?? ""}
                          onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                          data-testid={`${testidPrefix}-field-${f.key}`}
                        >
                          <option value="">— Select —</option>
                          {(f.options || []).map((o) => (
                            <option key={o.value || o} value={o.value || o}>{o.label || o}</option>
                          ))}
                        </select>
                      ) : (
                        <Input
                          type={f.type === "number" ? "number" : f.type === "date" ? "date" : "text"}
                          value={form[f.key] ?? ""}
                          onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                          className="h-9 rounded-sm"
                          data-testid={`${testidPrefix}-field-${f.key}`}
                        />
                      )}
                    </div>
                  ))}
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setOpen(false)} className="rounded-sm" data-testid={`${testidPrefix}-cancel-btn`}>Cancel</Button>
                  <Button onClick={save} className="rounded-sm" data-testid={`${testidPrefix}-save-btn`}>Save</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          )}
        </div>
      </div>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40 hover:bg-muted/40">
              {columns.map((c) => (
                <TableHead key={c.key} className="text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground">{c.label}</TableHead>
              ))}
              {(onUpdate || onDelete) && <TableHead className="w-24 text-right">Actions</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.length === 0 && (
              <TableRow>
                <TableCell colSpan={columns.length + 1} className="text-center text-sm text-muted-foreground py-10">No records.</TableCell>
              </TableRow>
            )}
            {filtered.map((row) => (
              <TableRow key={row.id} className="hover:bg-muted/30">
                {columns.map((c) => (
                  <TableCell key={c.key} className="py-2.5 text-sm">
                    {c.render ? c.render(row) : c.badge ? <StatusBadge {...c.badge(row)} /> : row[c.key] ?? "—"}
                  </TableCell>
                ))}
                {(onUpdate || onDelete) && (
                  <TableCell className="text-right">
                    <div className="inline-flex gap-1">
                      {onUpdate && canWrite && (
                        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => startEdit(row)} data-testid={`${testidPrefix}-edit-${row.id}`}>
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                      )}
                      {onDelete && canDelete && (
                        <Button size="icon" variant="ghost" className="h-7 w-7 text-destructive" onClick={() => onDelete(row.id)} data-testid={`${testidPrefix}-delete-${row.id}`}>
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </div>
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <div className="px-4 py-2 border-t border-border text-xs text-muted-foreground">
        Showing <span className="text-foreground font-semibold">{filtered.length}</span> of {data.length}
      </div>
    </div>
  );
}

export function StatusBadge({ text, tone = "neutral" }) {
  const map = {
    neutral: "bg-muted text-foreground border-border",
    success: "bg-success/15 text-success border-success/30",
    warning: "bg-warning/15 text-warning border-warning/30",
    danger: "bg-destructive/15 text-destructive border-destructive/30",
    info: "bg-chart-3/15 text-chart-3 border-chart-3/30",
    primary: "bg-primary/15 text-primary border-primary/30",
  };
  return (
    <span className={cn("inline-flex items-center px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider border rounded-sm", map[tone])}>
      {text}
    </span>
  );
}
