import { useState, useMemo, useEffect } from "react";
import { Plus, Search, Trash2, Pencil, FileSpreadsheet, FileText, Paperclip, ArrowUp, ArrowDown, ArrowUpDown, Loader2 } from "lucide-react";
import TablePager from "@/components/TablePager";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { downloadExport } from "@/lib/exports";
import RowAttachments from "@/components/RowAttachments";
import useSearchLanding from "@/hooks/useSearchLanding";

/**
 * Generic data table with create/edit/delete dialog.
 * columns: [{ key, label, render?, badge?: (row) => ({text, tone}) }]
 * fields: [{ key, label, type?: 'text'|'number'|'select'|'textarea'|'date', options?: [] }]
 * attachmentsParentType?: string  -> when set, enables a paperclip button per row
 *   that opens a drag-drop attachments dialog bound to (parent_type, row.id).
 */
function FormField({ field, value, onChange, testidPrefix }) {
  const testId = `${testidPrefix}-field-${field.key}`;
  if (field.type === "textarea") {
    return (
      <textarea
        className="w-full min-h-[80px] rounded-sm border border-input bg-background p-2 text-sm"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        data-testid={testId}
      />
    );
  }
  if (field.type === "multiselect") {
    const arr = Array.isArray(value) ? value : (value ? [value] : []);
    const toggle = (opt) => {
      const next = arr.includes(opt) ? arr.filter((x) => x !== opt) : [...arr, opt];
      onChange(next);
    };
    return (
      <div className="flex flex-wrap gap-1.5 p-2 border border-input rounded-sm bg-background min-h-9" data-testid={testId}>
        {(field.options || []).map((o) => {
          const v = o.value || o;
          const label = o.label || o;
          const active = arr.includes(v);
          return (
            <button
              key={v}
              type="button"
              onClick={() => toggle(v)}
              className={cn(
                "text-[11px] font-bold uppercase tracking-wider px-2 py-1 rounded-sm border transition-colors",
                active
                  ? "bg-primary text-primary-foreground border-primary"
                  : "border-border text-muted-foreground hover:border-primary/40",
              )}
              data-testid={`${testId}-opt-${v}`}
            >
              {label}
            </button>
          );
        })}
        {arr.length === 0 && <span className="text-[11px] text-muted-foreground self-center">None selected</span>}
      </div>
    );
  }
  if (field.type === "checkbox") {
    return (
      <label className="inline-flex items-center gap-2 text-sm" data-testid={testId}>
        <input
          type="checkbox"
          checked={!!value}
          onChange={(e) => onChange(e.target.checked)}
          className="h-4 w-4 rounded-sm border-input"
        />
        {field.checkboxLabel || "Yes"}
      </label>
    );
  }
  if (field.type === "select") {
    return (
      <select
        className="h-9 rounded-sm border border-input bg-background px-2 text-sm"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        data-testid={testId}
      >
        <option value="">— Select —</option>
        {(field.options || []).map((o) => (
          <option key={o.value || o} value={o.value || o}>{o.label || o}</option>
        ))}
      </select>
    );
  }
  let inputType = "text";
  if (field.type === "number") inputType = "number";
  else if (field.type === "date") inputType = "date";
  return (
    <Input
      type={inputType}
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value)}
      className="h-9 rounded-sm"
      data-testid={testId}
    />
  );
}

function RowActions({ row, onEdit, onDelete, canWrite, canDelete, testidPrefix, attachmentsParentType }) {
  const [openAttach, setOpenAttach] = useState(false);
  return (
    <div className="inline-flex gap-1">
      {attachmentsParentType && (
        <>
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7 text-primary"
            onClick={() => setOpenAttach(true)}
            data-testid={`${testidPrefix}-attach-${row.id}`}
            title="Attachments"
          >
            <Paperclip className="h-3.5 w-3.5" />
          </Button>
          <RowAttachments
            open={openAttach}
            onOpenChange={setOpenAttach}
            parentType={attachmentsParentType}
            parentId={row.id}
            recordTitle={row.name || row.title || row.po_no || row.code || row.id}
            testidPrefix={`${testidPrefix}-attach-${row.id}`}
          />
        </>
      )}
      {onEdit && canWrite && (
        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => onEdit(row)} data-testid={`${testidPrefix}-edit-${row.id}`}>
          <Pencil className="h-3.5 w-3.5" />
        </Button>
      )}
      {onDelete && canDelete && (
        <Button size="icon" variant="ghost" className="h-7 w-7 text-destructive" onClick={() => onDelete(row.id)} data-testid={`${testidPrefix}-delete-${row.id}`}>
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      )}
    </div>
  );
}

export default function DataTableShell({
  title,
  description,
  data,
  columns,
  fields,
  onCreate,
  onUpdate,
  onDelete,
  loadError,
  serverSearch,
  onServerSearch,
  serverTotal,
  footerExtra,
  testidPrefix = "tbl",
  searchKeys,
  rightSlot,
  exportResource,
  exportParams,
  canWrite = false,
  canDelete = false,
  attachmentsParentType,
  extraActions,
  formHeader,           // (mode: 'create'|'edit', form, setForm) => ReactNode — slot above the form
  onAfterCreate,        // async (createdRow, form) => void — fires after a successful create
  createDefaults,       // object — initial form values when creating a new record
  editFetch,            // async (row) => axios response — fetch full record before edit (all DB fields)
  pagination,           // from useResource().pagination — enables server-side search / sort / paging
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({});
  const serverMode = !!pagination;
  const searchValue = serverMode ? pagination.search : (onServerSearch ? serverSearch : query);
  const handleSearch = (v) => {
    if (serverMode) pagination.setSearch(v);
    else if (onServerSearch) onServerSearch(v);
    else setQuery(v);
  };
  useSearchLanding(handleSearch, [data]);

  const columnKeys = useMemo(() => (searchKeys || columns.map((c) => c.key)).filter((k) => k && !k.startsWith("_")), [columns, searchKeys]);
  useEffect(() => {
    if (serverMode) pagination.setSearchKeys(columnKeys.join(","));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverMode, columnKeys.join(",")]);

  const filtered = useMemo(() => {
    if (serverMode || onServerSearch) return data;
    if (!query) return data;
    const q = query.toLowerCase();
    const keys = searchKeys || columns.map((c) => c.key);
    return data.filter((row) => keys.some((k) => String(row?.[k] ?? "").toLowerCase().includes(q)));
  }, [data, query, columns, searchKeys, onServerSearch, serverMode]);

  const startCreate = () => {
    setEditing(null);
    setForm({ ...(createDefaults || {}) });
    setOpen(true);
  };
  const startEdit = async (row) => {
    let full = row;
    if (editFetch) {
      try { full = { ...row, ...(await editFetch(row)).data }; } catch { /* fall back to row */ }
    }
    setEditing(full);
    setForm({ ...full });
    setOpen(true);
  };

  const save = async () => {
    for (const f of fields) {
      if (f.required && (form[f.key] === undefined || form[f.key] === null || String(form[f.key]).trim() === "")) {
        toast.error(`${f.label} is required`);
        return;
      }
    }
    const payload = { ...form };
    fields.forEach((f) => {
      if (f.type === "number" && payload[f.key] !== undefined && payload[f.key] !== "") {
        payload[f.key] = Number(payload[f.key]);
      }
    });
    let created;
    if (editing) await onUpdate(editing.id, payload);
    else {
      created = await onCreate(payload);
      if (created && onAfterCreate) {
        try { await onAfterCreate(created, payload); } catch (_e) { /* parent toasts */ }
      }
    }
    setOpen(false);
  };

  const hasActions = onUpdate || onDelete || attachmentsParentType;

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
              placeholder={serverMode || onServerSearch ? "Search all records…" : "Search…"}
              className="pl-9 h-9 rounded-sm"
              value={searchValue}
              onChange={(e) => handleSearch(e.target.value)}
              data-testid={`${testidPrefix}-search`}
            />
          </div>
          {rightSlot}
          {extraActions}
          {exportResource && (
            <>
              <Button variant="outline" className="h-9 rounded-sm" onClick={() => downloadExport(exportResource, "xlsx", exportParams)} data-testid={`${testidPrefix}-export-xlsx`} title="Export Excel">
                <FileSpreadsheet className="h-4 w-4" />
              </Button>
              <Button variant="outline" className="h-9 rounded-sm" onClick={() => downloadExport(exportResource, "pdf", exportParams)} data-testid={`${testidPrefix}-export-pdf`} title="Export PDF">
                <FileText className="h-4 w-4" />
              </Button>
            </>
          )}
          {onCreate && canWrite && (
            <Button className="h-9 rounded-sm" onClick={startCreate} data-testid={`${testidPrefix}-add-btn`}>
              <Plus className="h-4 w-4 mr-1" /> New
            </Button>
          )}
          {(onCreate || onUpdate) && (
            <Dialog open={open} onOpenChange={setOpen}>
              <DialogContent className="max-w-3xl rounded-sm">
                <DialogHeader>
                  <DialogTitle className="font-display">{editing ? `Edit ${title}` : `New ${title}`}</DialogTitle>
                </DialogHeader>
                {formHeader && (
                  <div className="pb-2 border-b border-border mb-1">
                    {formHeader(editing ? "edit" : "create", form, setForm)}
                  </div>
                )}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 py-2 max-h-[70vh] overflow-y-auto pr-1">
                  {fields.map((f) => {
                    if (f.type === "section") {
                      return (
                        <div key={f.key} className="md:col-span-2 pt-2 first:pt-0">
                          <div className="flex items-center gap-2 pb-1.5 border-b border-border">
                            <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary">{f.label}</span>
                            {f.hint && <span className="text-[10px] text-muted-foreground">· {f.hint}</span>}
                          </div>
                        </div>
                      );
                    }
                    if (f.showIf && !f.showIf(form)) return null;
                    return (
                      <div key={f.key} className={cn("flex flex-col gap-1.5", f.full && "md:col-span-2")}>
                        <Label className="text-xs uppercase tracking-wider">
                          {f.label}{f.required && <span className="text-destructive ml-0.5">*</span>}
                        </Label>
                        <FormField
                          field={f}
                          value={form[f.key]}
                          onChange={(v) => setForm((s) => ({ ...s, [f.key]: v }))}
                          testidPrefix={testidPrefix}
                        />
                        {f.help && <div className="text-[10px] text-muted-foreground">{f.help}</div>}
                      </div>
                    );
                  })}
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
              {columns.map((c) => {
                const sortable = serverMode && c.key && !c.key.startsWith("_") && c.sortable !== false;
                const active = sortable && pagination.sort.by === c.key;
                return (
                  <TableHead
                    key={c.key}
                    className={cn("text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground", sortable && "cursor-pointer select-none hover:text-foreground")}
                    onClick={sortable ? () => pagination.setSort(c.key) : undefined}
                    aria-sort={active ? (pagination.sort.dir === "asc" ? "ascending" : "descending") : undefined}
                    data-testid={`${testidPrefix}-col-${c.key}`}
                  >
                    <span className="inline-flex items-center gap-1">
                      {c.label}
                      {sortable && (active
                        ? (pagination.sort.dir === "asc" ? <ArrowUp className="h-3 w-3 text-primary" /> : <ArrowDown className="h-3 w-3 text-primary" />)
                        : <ArrowUpDown className="h-3 w-3 opacity-30" />)}
                    </span>
                  </TableHead>
                );
              })}
              {hasActions && <TableHead className="w-28 text-right">Actions</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.length === 0 && (
              <TableRow>
                <TableCell colSpan={columns.length + 1} className="text-center text-sm py-10">
                  {loadError
                    ? <span className="text-rose-600" data-testid="table-load-error">{loadError}</span>
                    : serverMode && pagination.loading
                      ? <span className="text-muted-foreground inline-flex items-center gap-2" data-testid={`${testidPrefix}-loading`}><Loader2 className="h-4 w-4 animate-spin" /> Loading…</span>
                      : <span className="text-muted-foreground">No records.</span>}
                </TableCell>
              </TableRow>
            )}
            {filtered.map((row) => (
              <TableRow key={row.id} className="hover:bg-muted/30" data-row-id={row.id}>
                {columns.map((c) => {
                  let cellContent;
                  if (c.render) cellContent = c.render(row);
                  else if (c.badge) cellContent = <StatusBadge {...c.badge(row)} />;
                  else cellContent = row[c.key] ?? "—";
                  return (
                    <TableCell key={c.key} className="py-2.5 text-sm">{cellContent}</TableCell>
                  );
                })}
                {hasActions && (
                  <TableCell className="text-right">
                    <RowActions
                      row={row}
                      onEdit={onUpdate ? startEdit : null}
                      onDelete={onDelete}
                      canWrite={canWrite}
                      canDelete={canDelete}
                      testidPrefix={testidPrefix}
                      attachmentsParentType={attachmentsParentType}
                    />
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <div className="px-4 py-2 border-t border-border text-xs text-muted-foreground">
        {serverMode ? (
          <TablePager pagination={pagination} testidPrefix={testidPrefix} />
        ) : (
          <>
            Showing <span className="text-foreground font-semibold">{filtered.length}</span> of {serverTotal ?? data.length}
            {footerExtra}
          </>
        )}
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
