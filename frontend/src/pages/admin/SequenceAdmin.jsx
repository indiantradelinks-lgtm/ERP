import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Hash, RefreshCw, RotateCcw, Trash2, AlertTriangle, CheckCircle2 } from "lucide-react";
import { api, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";

export default function SequenceAdmin() {
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(new Set());
  const [confirmForce, setConfirmForce] = useState(false);

  const load = async () => {
    setBusy(true);
    try { const { data } = await api.get("/admin/sequences"); setRows(data || []); }
    catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setBusy(false); }
  };
  useEffect(() => { load(); }, []);

  const filtered = rows.filter((r) =>
    !search || r.key.toLowerCase().includes(search.toLowerCase())
  );

  const toggleAll = () => {
    if (selected.size === filtered.length) setSelected(new Set());
    else setSelected(new Set(filtered.map((r) => r.key)));
  };

  const reset = async (mode, keysArr) => {
    const label = mode === "force" ? "HARD reset to 0" : "auto-sync to max-in-data";
    if (mode === "force" && !confirmForce) {
      toast.error("Tick 'I understand' first — force mode can cause duplicate doc numbers if data still exists.");
      return;
    }
    if (!confirm(`${label} for ${keysArr ? keysArr.length : "ALL " + rows.length} counter(s)?`)) return;
    setBusy(true);
    try {
      const { data } = await api.post("/admin/sequences/reset", { mode, keys: keysArr });
      toast.success(`${data.reset_count} counter${data.reset_count === 1 ? "" : "s"} reset (${mode}).`);
      setSelected(new Set());
      await load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setBusy(false); }
  };

  const deleteKey = async (key) => {
    if (!confirm(`Delete counter '${key}'? Next allocation will restart from 0001.`)) return;
    setBusy(true);
    try {
      await api.delete(`/admin/sequences/${encodeURIComponent(key)}`);
      toast.success(`Counter ${key} deleted.`);
      await load();
    } catch (e) { toast.error(apiErrorMessage(e)); }
    finally { setBusy(false); }
  };

  const totalDrift = rows.reduce((sum, r) => sum + Math.max(0, r.drift), 0);
  const safeZeroCount = rows.filter((r) => r.can_safely_reset_to_zero).length;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6" data-testid="sequence-admin">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Hash className="h-6 w-6 text-primary" /> Document Sequence Manager
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Resets the auto-numbering counters after test-data cleanup so new docs start from 0001.
          </p>
        </div>
        <Button variant="outline" onClick={load} disabled={busy} data-testid="seq-refresh">
          <RefreshCw className="h-4 w-4 mr-1.5" /> Refresh
        </Button>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Kpi label="Total Counters" value={rows.length} tone="bg-blue-50 border-blue-200 text-blue-900" />
        <Kpi label="Safe to reset → 1" value={safeZeroCount} tone="bg-emerald-50 border-emerald-200 text-emerald-900"
             hint="No real records use this prefix anymore" />
        <Kpi label="Total Drift" value={`+${totalDrift}`} tone="bg-amber-50 border-amber-200 text-amber-900"
             hint="Sum of (current - max-in-data) across all counters" />
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center gap-3 flex-wrap">
          <CardTitle className="text-base flex-1">Counters</CardTitle>
          <Input
            placeholder="Filter prefix…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="max-w-xs"
            data-testid="seq-search"
          />
          <Button
            variant="outline"
            disabled={busy || selected.size === 0}
            onClick={() => reset("auto", Array.from(selected))}
            data-testid="seq-reset-auto-selected"
          >
            <RotateCcw className="h-4 w-4 mr-1.5" /> Auto-sync selected ({selected.size})
          </Button>
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => reset("auto", null)}
            data-testid="seq-reset-auto-all"
          >
            <RotateCcw className="h-4 w-4 mr-1.5" /> Auto-sync ALL
          </Button>
          <Button
            className="bg-rose-600 hover:bg-rose-700 text-white"
            disabled={busy || !confirmForce}
            onClick={() => reset("force", selected.size > 0 ? Array.from(selected) : null)}
            data-testid="seq-force-reset"
          >
            <AlertTriangle className="h-4 w-4 mr-1.5" />
            Force → 0 {selected.size > 0 ? `(${selected.size})` : "(ALL)"}
          </Button>
        </CardHeader>
        <CardContent>
          <label className="flex items-center gap-2 text-xs mb-3">
            <input
              type="checkbox"
              checked={confirmForce}
              onChange={(e) => setConfirmForce(e.target.checked)}
              data-testid="seq-confirm-force"
            />
            <span className="text-rose-700 font-medium">
              I understand: <strong>force</strong> mode zeroes the counter without checking data — if any existing
              document still uses the prefix, next allocation will collide with it. Use <strong>auto-sync</strong>
              for safe resets.
            </span>
          </label>

          <div className="border rounded-sm overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="p-2 w-8">
                    <input
                      type="checkbox"
                      checked={selected.size === filtered.length && filtered.length > 0}
                      onChange={toggleAll}
                      data-testid="seq-select-all"
                    />
                  </th>
                  <th className="text-left p-2">Counter Key</th>
                  <th className="text-right p-2">Current</th>
                  <th className="text-right p-2">Max in Data</th>
                  <th className="text-right p-2">Drift</th>
                  <th className="text-center p-2">Next Allocation (auto)</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 && (
                  <tr><td colSpan={7} className="p-8 text-center text-muted-foreground">No counters match the filter.</td></tr>
                )}
                {filtered.map((r) => {
                  const checked = selected.has(r.key);
                  const nextAfterAuto = r.max_in_data + 1;
                  return (
                    <tr key={r.key} className="border-t hover:bg-slate-50" data-testid={`seq-row-${r.key}`}>
                      <td className="p-2 text-center">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => {
                            const s = new Set(selected);
                            checked ? s.delete(r.key) : s.add(r.key);
                            setSelected(s);
                          }}
                          data-testid={`seq-pick-${r.key}`}
                        />
                      </td>
                      <td className="p-2 font-mono text-xs">{r.key}</td>
                      <td className="p-2 text-right font-mono">{r.current_value}</td>
                      <td className="p-2 text-right font-mono">{r.max_in_data}</td>
                      <td className="p-2 text-right">
                        {r.drift > 0 ? (
                          <Badge className="bg-amber-100 text-amber-700 font-mono">+{r.drift}</Badge>
                        ) : (
                          <Badge className="bg-emerald-100 text-emerald-700 font-mono">{r.drift}</Badge>
                        )}
                      </td>
                      <td className="p-2 text-center">
                        <Badge variant="outline" className="font-mono">
                          {r.can_safely_reset_to_zero ? (
                            <><CheckCircle2 className="h-3 w-3 mr-1 text-emerald-600 inline" /> 0001</>
                          ) : (
                            String(nextAfterAuto).padStart(4, "0")
                          )}
                        </Badge>
                      </td>
                      <td className="p-2 text-right">
                        <Button
                          size="sm" variant="ghost"
                          className="text-rose-600 hover:bg-rose-50"
                          onClick={() => deleteKey(r.key)}
                          title="Delete counter (next allocation restarts from 0001)"
                          data-testid={`seq-delete-${r.key}`}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function Kpi({ label, value, tone, hint }) {
  return (
    <div className={`p-4 border rounded-sm ${tone}`}>
      <div className="text-xs uppercase tracking-wider opacity-80">{label}</div>
      <div className="text-3xl font-bold mt-1">{value}</div>
      {hint && <div className="text-[10px] opacity-70 mt-1">{hint}</div>}
    </div>
  );
}
