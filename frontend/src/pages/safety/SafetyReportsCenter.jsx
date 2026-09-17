/**
 * Safety Reports Center (Phase 5) — 32 canned reports with filter bar,
 * live preview table and Excel / PDF export.
 */
import { useEffect, useMemo, useState } from "react";
import { api, API } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FileSpreadsheet, FileText, RefreshCcw, Search } from "lucide-react";
import { fmtDT, fmtT } from "@/lib/datetime";

export default function SafetyReportsCenter() {
  const [keys, setKeys] = useState([]);
  const [activeKey, setActiveKey] = useState("");
  const [projects, setProjects] = useState([]);
  const [filters, setFilters] = useState({ from: "", to: "", project_id: "", site: "", client: "", risk: "", status: "", responsible: "" });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");

  const loadKeys = async () => {
    try {
      const [a, b] = await Promise.all([api.get("/safety/reports/keys"), api.get("/projects")]);
      setKeys(a.data || []); setProjects(b.data || []);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load"); }
  };
  useEffect(() => { loadKeys(); }, []);

  const filteredKeys = useMemo(() => {
    if (!search) return keys;
    const s = search.toLowerCase();
    return keys.filter((k) => k.label.toLowerCase().includes(s) || k.key.includes(s));
  }, [keys, search]);

  const runReport = async () => {
    if (!activeKey) return;
    setLoading(true);
    try {
      const q = new URLSearchParams();
      Object.entries(filters).forEach(([k, v]) => { if (v) q.set(k, v); });
      const r = await api.get(`/safety/reports/${activeKey}?${q.toString()}`);
      setData(r.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Report failed"); }
    finally { setLoading(false); }
  };
  useEffect(() => { if (activeKey) runReport(); }, [activeKey]);

  const exportUrl = (fmt) => {
    const q = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => { if (v) q.set(k, v); });
    q.set("format", fmt);
    return `${API}/safety/reports/${activeKey}?${q.toString()}`;
  };

  const download = async (fmt) => {
    if (!activeKey) return;
    try {
      const q = new URLSearchParams();
      Object.entries(filters).forEach(([k, v]) => { if (v) q.set(k, v); });
      q.set("format", fmt);
      const res = await api.get(`/safety/reports/${activeKey}?${q.toString()}`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${activeKey}.${fmt}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error("Export failed"); }
  };

  return (
    <div className="flex h-[calc(100vh-4rem)]" data-testid="reports-center-page">
      {/* Left: report picker */}
      <aside className="w-72 border-r bg-slate-50/40 flex flex-col">
        <div className="p-3 border-b">
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1">Safety · Reports</div>
          <div className="relative">
            <Search className="h-3.5 w-3.5 absolute left-2 top-2.5 text-slate-400" />
            <Input className="pl-7 h-8 text-xs" placeholder="Search reports…" value={search} onChange={(e) => setSearch(e.target.value)} data-testid="reports-search" />
          </div>
        </div>
        <div className="overflow-y-auto flex-1 py-1">
          {filteredKeys.map((k) => (
            <button
              key={k.key}
              onClick={() => setActiveKey(k.key)}
              className={`w-full text-left text-xs px-3 py-2 border-l-2 transition-colors ${activeKey === k.key ? "border-red-600 bg-red-50/50 font-semibold" : "border-transparent hover:bg-slate-100"}`}
              data-testid={`rpt-${k.key}`}
            >
              {k.label}
            </button>
          ))}
        </div>
      </aside>

      {/* Right: viewer */}
      <main className="flex-1 overflow-y-auto p-6 space-y-4">
        {!activeKey ? (
          <div className="text-slate-400 text-sm">Pick a report from the left to run.</div>
        ) : (
          <>
            <div className="flex items-start justify-between flex-wrap gap-3">
              <div>
                <h1 className="font-display font-black text-2xl">{keys.find((k) => k.key === activeKey)?.label}</h1>
                <p className="text-xs text-muted-foreground mt-0.5">Live data from ERP. Filters below.</p>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" onClick={runReport} disabled={loading} data-testid="rpt-run">
                  <RefreshCcw className="h-3.5 w-3.5 mr-1" /> {loading ? "Running…" : "Run"}
                </Button>
                <Button variant="outline" onClick={() => download("xlsx")} data-testid="rpt-xlsx">
                  <FileSpreadsheet className="h-3.5 w-3.5 mr-1" /> Excel
                </Button>
                <Button variant="outline" onClick={() => download("pdf")} data-testid="rpt-pdf">
                  <FileText className="h-3.5 w-3.5 mr-1" /> PDF
                </Button>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-2">
              <div><Label className="text-[10px] uppercase">From</Label><Input type="date" className="h-8 text-xs" value={filters.from} onChange={(e) => setFilters({ ...filters, from: e.target.value })} data-testid="fl-from" /></div>
              <div><Label className="text-[10px] uppercase">To</Label><Input type="date" className="h-8 text-xs" value={filters.to} onChange={(e) => setFilters({ ...filters, to: e.target.value })} data-testid="fl-to" /></div>
              <div>
                <Label className="text-[10px] uppercase">Project</Label>
                <select className="w-full border rounded h-8 px-1 text-xs" value={filters.project_id} onChange={(e) => setFilters({ ...filters, project_id: e.target.value })} data-testid="fl-project">
                  <option value="">All</option>
                  {projects.map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}
                </select>
              </div>
              <div><Label className="text-[10px] uppercase">Site</Label><Input className="h-8 text-xs" value={filters.site} onChange={(e) => setFilters({ ...filters, site: e.target.value })} /></div>
              <div><Label className="text-[10px] uppercase">Client</Label><Input className="h-8 text-xs" value={filters.client} onChange={(e) => setFilters({ ...filters, client: e.target.value })} /></div>
              <div>
                <Label className="text-[10px] uppercase">Risk</Label>
                <select className="w-full border rounded h-8 px-1 text-xs" value={filters.risk} onChange={(e) => setFilters({ ...filters, risk: e.target.value })}>
                  <option value="">Any</option><option>low</option><option>medium</option><option>high</option><option>critical</option>
                </select>
              </div>
              <div><Label className="text-[10px] uppercase">Status</Label><Input className="h-8 text-xs" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })} /></div>
              <div><Label className="text-[10px] uppercase">Responsible</Label><Input className="h-8 text-xs" value={filters.responsible} onChange={(e) => setFilters({ ...filters, responsible: e.target.value })} /></div>
            </div>

            {data && (
              <div className="border rounded-sm bg-card overflow-hidden">
                <div className="px-3 py-2 border-b bg-slate-50 flex items-center justify-between">
                  <div className="text-xs font-bold uppercase tracking-wider text-slate-600">
                    {data.count} row{data.count === 1 ? "" : "s"} · generated {fmtT(data.generated_at)}
                  </div>
                </div>
                <div className="overflow-x-auto max-h-[60vh] overflow-y-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-slate-50 sticky top-0 text-[10px] uppercase tracking-wider text-slate-600">
                      <tr>
                        {data.columns.map((c) => (
                          <th key={c} className="text-left px-3 py-2 border-b">{c.replace(/_/g, " ")}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {data.rows.length === 0 && (
                        <tr><td colSpan={data.columns.length} className="text-center py-8 text-slate-400">No rows.</td></tr>
                      )}
                      {data.rows.map((r, i) => (
                        <tr key={i} className="border-t hover:bg-slate-50/40">
                          {data.columns.map((c) => (
                            <td key={c} className="px-3 py-1.5">{formatCell(r[c])}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}

function formatCell(v) {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "✔" : "✗";
  if (typeof v === "number") return v.toLocaleString("en-IN");
  const s = String(v);
  if (/^\d{4}-\d{2}-\d{2}T/.test(s)) return fmtDT(s);
  return s;
}
