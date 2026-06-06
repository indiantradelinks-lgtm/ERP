import { useEffect, useMemo, useState } from "react";
import { Boxes, Upload, Download, BarChart3, AlertTriangle, Clock, TrendingUp, Layers, Bell, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { StatusBadge } from "@/components/DataTableShell";
import { api } from "@/lib/api";
import { toast } from "sonner";

const inr = (n) => "₹ " + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });

const TABS = [
  { id: "valuation", label: "Valuation (FIFO/LIFO)", icon: Layers },
  { id: "aging", label: "Aging", icon: Clock },
  { id: "dead-stock", label: "Dead Stock", icon: AlertTriangle },
  { id: "movers", label: "Fast / Slow", icon: TrendingUp },
  { id: "idle", label: "Idle Inventory", icon: Boxes },
  { id: "reorder", label: "Reorder Alerts", icon: Bell },
  { id: "import", label: "Bulk Import", icon: Upload },
];

export default function InventoryIntel() {
  const [active, setActive] = useState("valuation");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [valMethod, setValMethod] = useState("fifo");
  const [days, setDays] = useState(90);

  const load = async () => {
    if (active === "import") { setData(null); return; }
    setLoading(true); setData(null);
    let url = "";
    if (active === "valuation") url = `/inventory-intel/valuation?method=${valMethod}`;
    else if (active === "aging") url = "/inventory-intel/reports/aging";
    else if (active === "dead-stock") url = `/inventory-intel/reports/dead-stock?days=${days}`;
    else if (active === "movers") url = `/inventory-intel/reports/movers?days=${days}`;
    else if (active === "idle") url = `/inventory-intel/reports/idle?days=${days}`;
    else if (active === "reorder") url = "/inventory-intel/reorder-alerts";
    try {
      const { data } = await api.get(url);
      setData(data);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [active, valMethod, days]);

  return (
    <div className="space-y-6" data-testid="inventory-intel-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <BarChart3 className="h-3 w-3" /> Procurement · Inventory Intelligence
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Inventory Intelligence</h1>
        <p className="text-sm text-muted-foreground mt-1">FIFO/LIFO valuation, aging, dead-stock, fast/slow movers, idle inventory, reorder alerts, and bulk Excel/CSV import.</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <Button key={t.id} variant={active === t.id ? "default" : "outline"} className="rounded-sm h-9" onClick={() => setActive(t.id)} data-testid={`intel-tab-${t.id}`}>
              <Icon className="h-3.5 w-3.5 mr-1.5" /> {t.label}
            </Button>
          );
        })}
      </div>

      {(active === "dead-stock" || active === "movers" || active === "idle") && (
        <div className="flex items-center gap-2 bg-muted/30 border border-border rounded-sm p-2 w-fit">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Window (days)</span>
          {[30, 60, 90, 180, 365].map((d) => (
            <Button key={d} size="sm" variant={days === d ? "default" : "outline"} className="h-7 rounded-sm" onClick={() => setDays(d)} data-testid={`intel-days-${d}`}>{d}d</Button>
          ))}
        </div>
      )}

      <div className="bg-card border border-border rounded-sm p-5 min-h-[260px]" data-testid={`intel-pane-${active}`}>
        {loading && <div className="text-sm text-muted-foreground">Loading…</div>}
        {!loading && active === "valuation" && <Valuation data={data} method={valMethod} setMethod={setValMethod} />}
        {!loading && active === "aging" && <Aging data={data} />}
        {!loading && active === "dead-stock" && <DeadStock data={data} />}
        {!loading && active === "movers" && <Movers data={data} />}
        {!loading && active === "idle" && <Idle data={data} />}
        {!loading && active === "reorder" && <Reorder data={data} />}
        {active === "import" && <Importer onDone={() => setActive("valuation")} />}
      </div>
    </div>
  );
}

function Valuation({ data, method, setMethod }) {
  if (!data?.items) return <Empty />;
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Method</span>
        {["fifo", "lifo", "weighted_avg"].map((m) => (
          <Button key={m} size="sm" variant={method === m ? "default" : "outline"} className="h-7 rounded-sm uppercase tracking-wider" onClick={() => setMethod(m)} data-testid={`val-method-${m}`}>
            {m.replace("_", " ")}
          </Button>
        ))}
        <div className="ml-auto text-sm font-bold">Total: <span className="font-display text-2xl text-primary tabular">{inr(data.total_value)}</span></div>
      </div>
      <Table>
        <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
          <TableHead className="text-[10px] uppercase tracking-wider">Item</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">On hand</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Effective rate</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Value</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Layers</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {data.items.map((r) => (
            <TableRow key={r.item_id} data-testid={`val-row-${r.item_id}`}>
              <TableCell className="text-sm font-semibold">{r.name}</TableCell>
              <TableCell className="font-mono-data text-sm tabular">{r.quantity} {r.unit}</TableCell>
              <TableCell className="font-mono-data text-sm tabular">{inr(r.weighted_rate)}</TableCell>
              <TableCell className="font-mono-data text-sm tabular font-bold">{inr(r.value)}</TableCell>
              <TableCell className="text-[10px] text-muted-foreground">
                {(r.layers || []).slice(0, 3).map((l, i) => <div key={i}>{l.qty} @ {inr(l.rate)} · {l.received_at}</div>)}
                {(r.layers || []).length > 3 && <div>+{r.layers.length - 3} more</div>}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function Aging({ data }) {
  if (!data?.buckets) return <Empty />;
  const buckets = Object.entries(data.buckets);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
        {buckets.map(([k, rows]) => (
          <div key={k} className="bg-muted/30 border border-border rounded-sm p-3" data-testid={`aging-bucket-${k}`}>
            <div className="text-[9px] uppercase tracking-wider text-muted-foreground">{k}</div>
            <div className="font-display font-black text-2xl tabular mt-1 text-primary">{rows.length}</div>
            <div className="text-[10px] text-muted-foreground tabular">{inr(rows.reduce((a, r) => a + (r.value || 0), 0))}</div>
          </div>
        ))}
      </div>
      {buckets.map(([k, rows]) => rows.length > 0 && (
        <div key={k}>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-2">{k} ({rows.length})</div>
          <Table>
            <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
              <TableHead className="text-[10px] uppercase tracking-wider">Item</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Code</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Qty</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Value</TableHead>
              <TableHead className="text-[10px] uppercase tracking-wider">Age</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.id}><TableCell className="text-sm font-semibold">{r.name}</TableCell><TableCell className="font-mono-data text-xs">{r.code || "—"}</TableCell><TableCell className="font-mono-data text-sm tabular">{r.quantity} {r.unit}</TableCell><TableCell className="font-mono-data text-sm tabular">{inr(r.value)}</TableCell><TableCell className="text-xs">{r.age_days != null ? `${r.age_days} d` : "—"}</TableCell></TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ))}
    </div>
  );
}

function DeadStock({ data }) {
  if (!data?.items) return <Empty />;
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 text-sm">
        <span className="text-muted-foreground">{data.count} items not issued in last {data.days_threshold} days</span>
        <span className="ml-auto font-bold">Total locked: <span className="text-destructive text-lg">{inr(data.total_value)}</span></span>
      </div>
      <Table>
        <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
          <TableHead className="text-[10px] uppercase tracking-wider">Item</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Qty</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Rate</TableHead>
          <TableHead className="text-[10px] uppercase tracking-wider">Value</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {data.items.length === 0 && <TableRow><TableCell colSpan={4} className="text-center text-muted-foreground py-6 text-sm">No dead stock 🎉</TableCell></TableRow>}
          {data.items.map((r, i) => (
            <TableRow key={`${r.id}-${i}`} data-testid={`dead-row-${r.id}`}><TableCell className="text-sm font-semibold">{r.name}<div className="text-[10px] text-muted-foreground">{r.code || ""}</div></TableCell><TableCell className="font-mono-data text-sm tabular">{r.quantity} {r.unit}</TableCell><TableCell className="font-mono-data text-sm tabular">{inr(r.rate)}</TableCell><TableCell className="font-mono-data text-sm tabular text-destructive font-bold">{inr(r.value)}</TableCell></TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function Movers({ data }) {
  if (!data?.fast_movers && !data?.slow_movers) return <Empty />;
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <Bucket title={`Fast Movers (last ${data.days_window} d)`} tone="success" rows={data.fast_movers}
        cols={[["Item", "name"], ["Out", "total_out"], ["On hand", "on_hand"], ["Reorder", "reorder_level"]]}
        testid="movers-fast" />
      <Bucket title={`Slow Movers (no outward in ${data.days_window} d)`} tone="danger" rows={data.slow_movers}
        cols={[["Item", "name"], ["On hand", "on_hand"], ["Value", "value"]]}
        testid="movers-slow" valueKey="value" />
    </div>
  );
}

function Bucket({ title, tone, rows, cols, testid, valueKey }) {
  const c = { success: "text-success", danger: "text-destructive" }[tone];
  return (
    <div data-testid={testid}>
      <div className={`text-[10px] font-bold uppercase tracking-[0.18em] mb-2 ${c}`}>{title} ({rows?.length || 0})</div>
      <Table>
        <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">{cols.map(([l]) => <TableHead key={l} className="text-[10px] uppercase tracking-wider">{l}</TableHead>)}</TableRow></TableHeader>
        <TableBody>
          {(rows || []).length === 0 && <TableRow><TableCell colSpan={cols.length} className="text-center text-muted-foreground py-6 text-sm">No data</TableCell></TableRow>}
          {(rows || []).map((r, i) => (
            <TableRow key={`${r.item_id}-${i}`}>
              {cols.map(([l, k]) => (
                <TableCell key={l} className={`text-sm ${k === valueKey ? "font-bold tabular" : ""} ${k === "name" ? "font-semibold" : "font-mono-data tabular"}`}>
                  {k === "value" ? inr(r[k]) : r[k] ?? "—"}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function Idle({ data }) {
  if (!data?.items) return <Empty />;
  return (
    <div className="space-y-3">
      <div className="text-sm text-muted-foreground">{data.count} items with no movement in last {data.days_window} days</div>
      <Table>
        <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40"><TableHead className="text-[10px] uppercase tracking-wider">Item</TableHead><TableHead className="text-[10px] uppercase tracking-wider">On hand</TableHead><TableHead className="text-[10px] uppercase tracking-wider">Value</TableHead></TableRow></TableHeader>
        <TableBody>
          {data.items.length === 0 && <TableRow><TableCell colSpan={3} className="text-center text-muted-foreground py-6 text-sm">No idle stock</TableCell></TableRow>}
          {data.items.map((r) => (
            <TableRow key={r.id}><TableCell className="text-sm font-semibold">{r.name}</TableCell><TableCell className="font-mono-data text-sm tabular">{r.quantity} {r.unit}</TableCell><TableCell className="font-mono-data text-sm tabular text-warning">{inr(r.value)}</TableCell></TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function Reorder({ data }) {
  if (!data?.items) return <Empty />;
  const sevTone = { critical: "danger", high: "warning", warning: "info" };
  return (
    <div className="space-y-3">
      <div className="text-sm">
        <span className="text-muted-foreground">{data.count} items at or below reorder level</span>
        {data.count === 0 && <span className="ml-2 text-success font-bold">✓ Healthy</span>}
      </div>
      <Table>
        <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40"><TableHead className="text-[10px] uppercase tracking-wider">Severity</TableHead><TableHead className="text-[10px] uppercase tracking-wider">Item</TableHead><TableHead className="text-[10px] uppercase tracking-wider">On hand</TableHead><TableHead className="text-[10px] uppercase tracking-wider">Reorder Lvl</TableHead><TableHead className="text-[10px] uppercase tracking-wider">Vendor</TableHead></TableRow></TableHeader>
        <TableBody>
          {data.items.length === 0 && <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground py-6 text-sm">No alerts.</TableCell></TableRow>}
          {data.items.map((r) => (
            <TableRow key={r.id} data-testid={`reorder-row-${r.id}`}>
              <TableCell><StatusBadge text={r.severity} tone={sevTone[r.severity] || "neutral"} /></TableCell>
              <TableCell className="text-sm font-semibold">{r.name}<div className="text-[10px] text-muted-foreground">{r.code || ""}</div></TableCell>
              <TableCell className="font-mono-data text-sm tabular">{r.quantity} {r.unit}</TableCell>
              <TableCell className="font-mono-data text-sm tabular text-muted-foreground">{r.reorder_level}</TableCell>
              <TableCell className="text-xs">{r.vendor_name || "—"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function Importer({ onDone }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const download = async () => {
    try {
      const res = await api.get("/inventory-intel/import-template", { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a"); a.href = url; a.download = "inventory_template.csv"; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error("Template download failed"); }
  };

  const upload = async () => {
    if (!file) { toast.error("Pick a CSV file first"); return; }
    setBusy(true);
    try {
      const form = new FormData(); form.append("file", file);
      const { data } = await api.post("/inventory-intel/import.csv", form, { headers: { "Content-Type": "multipart/form-data" } });
      setResult(data);
      toast.success(`Created ${data.summary.created} · Updated ${data.summary.updated} · Errors ${data.summary.errors}`);
    } catch (e) { toast.error(e.response?.data?.detail || "Import failed"); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      <div className="bg-muted/30 border border-border rounded-sm p-4 space-y-2">
        <div className="text-[10px] uppercase tracking-wider text-primary font-bold">Step 1 — Get the template</div>
        <p className="text-xs text-muted-foreground">CSV columns: item_code, name, category, unit, opening_quantity, rate, store_location, batch, serial_no, vendor_name, asset_tag, reorder_level, min_stock, max_stock. Quantity is added to existing stock if item_code or name matches.</p>
        <Button variant="outline" className="rounded-sm h-9" onClick={download} data-testid="intel-import-template"><Download className="h-4 w-4 mr-1.5" /> Download template</Button>
      </div>
      <div className="bg-muted/30 border border-border rounded-sm p-4 space-y-2">
        <div className="text-[10px] uppercase tracking-wider text-primary font-bold">Step 2 — Upload your filled file</div>
        <div className="flex gap-2 flex-wrap items-center">
          <input type="file" accept=".csv,.tsv,.txt" onChange={(e) => { setFile(e.target.files?.[0] || null); setResult(null); }} className="text-sm" data-testid="intel-import-file" />
          <Button className="rounded-sm h-9" onClick={upload} disabled={busy || !file} data-testid="intel-import-go">
            <Upload className="h-4 w-4 mr-1.5" /> {busy ? "Uploading…" : "Import"}
          </Button>
        </div>
      </div>
      {result && (
        <div className="border border-border rounded-sm p-4" data-testid="intel-import-result">
          <div className="flex items-center justify-between mb-2">
            <div className="text-[10px] uppercase tracking-wider text-primary font-bold">Result</div>
            {result.summary?.errors === 0 && (
              <Button size="sm" variant="outline" className="h-8 rounded-sm" onClick={onDone} data-testid="intel-import-open-valuation">Open Valuation →</Button>
            )}
          </div>
          <div className="grid grid-cols-3 gap-3 mb-3">
            <Stat label="Created" value={result.summary.created} tone="success" />
            <Stat label="Updated" value={result.summary.updated} tone="info" />
            <Stat label="Errors" value={result.summary.errors} tone="danger" />
          </div>
          {result.errors.length > 0 && (
            <div className="text-xs text-destructive">
              <div className="font-bold mb-1">Errors:</div>
              <ul className="space-y-0.5">{result.errors.map((e, i) => <li key={`${e.row}-${i}`}>Row {e.row}: {e.error}</li>)}</ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, tone = "neutral" }) {
  const c = { success: "text-success", danger: "text-destructive", warning: "text-warning", info: "text-chart-3", neutral: "text-foreground" }[tone];
  return (<div className="bg-card border border-border rounded-sm p-3"><div className="text-[9px] uppercase tracking-wider text-muted-foreground">{label}</div><div className={`font-display font-black text-2xl tabular mt-1 ${c}`}>{value}</div></div>);
}

function Empty() { return <div className="text-sm text-muted-foreground text-center py-10">No data yet.</div>; }
