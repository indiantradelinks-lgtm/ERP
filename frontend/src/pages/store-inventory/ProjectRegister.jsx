/** Project Material Register — category-wise allocations per project with values (₹). */
import { useEffect, useState } from "react";
import { api, apiErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { Loader2, Download, FolderOpen } from "lucide-react";

const inr = (n) => "₹ " + Number(n || 0).toLocaleString("en-IN");

export function ProjectRegisterView() {
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("");
  const [reg, setReg] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get("/bulk-alloc/projects", { params: { all: true } }).then((r) => setProjects(r.data || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (!projectId) { setReg(null); return; }
    setLoading(true);
    api.get(`/bulk-alloc/project-register/${projectId}`)
      .then((r) => setReg(r.data))
      .catch((e) => toast.error(apiErrorMessage(e)))
      .finally(() => setLoading(false));
  }, [projectId]);

  const downloadExcel = async () => {
    try {
      const resp = await api.get(`/bulk-alloc/project-register/${projectId}/export`, { responseType: "blob" });
      const url = URL.createObjectURL(resp.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `material_register_${reg?.project?.code || projectId}.xlsx`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success("Register exported");
    } catch (e) { toast.error(apiErrorMessage(e)); }
  };

  return (
    <div data-testid="project-register-page">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3 mb-4">
        <div>
          <h1 className="font-display text-xl font-bold">Project Material Register</h1>
          <p className="text-sm text-slate-500">Category-wise materials issued to a project with values — for client billing & site reconciliation.</p>
        </div>
        {reg && (
          <Button variant="outline" className="rounded-sm" onClick={downloadExcel} data-testid="project-register-export">
            <Download className="h-4 w-4 mr-1.5" /> Excel
          </Button>
        )}
      </div>

      <div className="max-w-md mb-4">
        <Label className="text-xs uppercase tracking-wider">Project</Label>
        <select value={projectId} onChange={(e) => setProjectId(e.target.value)} data-testid="project-register-select"
          className="h-9 w-full rounded-sm border border-input bg-background px-2 text-sm mt-1">
          <option value="">— select project —</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name} ({p.status})</option>)}
        </select>
      </div>

      {loading && <div className="p-6 text-center text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin inline mr-2" />Loading register…</div>}

      {reg && !loading && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
            {[["Total Value", inr(reg.grand_total_value)],
              ["Total Tonnage", `${reg.grand_total_weight_mt ?? 0} MT`],
              ["Total Issued Qty", reg.grand_total_issued],
              ["Categories", reg.categories.length],
              ["Allocations", reg.total_allocations]].map(([l, v]) => (
              <div key={l} className="border rounded-sm p-3">
                <div className="text-[10px] uppercase tracking-wider text-slate-500">{l}</div>
                <div className="text-lg font-bold font-mono-data" data-testid={`project-register-kpi-${l.toLowerCase().replaceAll(" ", "-")}`}>{v}</div>
              </div>
            ))}
          </div>

          {reg.categories.length === 0 ? (
            <div className="p-10 text-center text-sm text-slate-500"><FolderOpen className="h-8 w-8 mx-auto mb-2 text-slate-300" />No materials allocated to this project yet</div>
          ) : (
            <div className="border rounded-sm overflow-x-auto">
              <table className="w-full text-sm" data-testid="project-register-table">
                <thead className="bg-slate-800 text-white text-xs uppercase tracking-wider">
                  <tr>
                    <th className="text-left px-3 py-2">Code</th>
                    <th className="text-left px-3 py-2">Item</th>
                    <th className="text-left px-2 py-2">Unit</th>
                    <th className="text-right px-2 py-2">Issued</th>
                    <th className="text-right px-2 py-2">Returned</th>
                    <th className="text-right px-2 py-2">Net</th>
                    <th className="text-right px-2 py-2">Weight (Kg)</th>
                    <th className="text-right px-3 py-2">Rate</th>
                    <th className="text-right px-3 py-2">Value</th>
                  </tr>
                </thead>
                <tbody>
                  {reg.categories.map((cat) => (
                    <CategoryRows key={cat.category} cat={cat} />
                  ))}
                  <tr className="border-t-2 border-slate-800 bg-slate-100 font-bold">
                    <td colSpan={3} className="px-3 py-2">GRAND TOTAL</td>
                    <td className="text-right px-2 font-mono-data">{reg.grand_total_issued}</td>
                    <td></td>
                    <td></td>
                    <td className="text-right px-2 font-mono-data" data-testid="project-register-grand-weight">{reg.grand_total_weight_kg} <span className="text-[10px] text-slate-500">({reg.grand_total_weight_mt} MT)</span></td>
                    <td></td>
                    <td className="text-right px-3 font-mono-data" data-testid="project-register-grand-total">{inr(reg.grand_total_value)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function CategoryRows({ cat }) {
  return (
    <>
      <tr className="bg-slate-50 border-t">
        <td colSpan={9} className="px-3 py-1.5 font-semibold text-slate-700 text-xs uppercase tracking-wider">{cat.category}</td>
      </tr>
      {cat.items.map((it) => (
        <tr key={it.code + it.item_name} className="border-t">
          <td className="px-3 py-1.5 font-mono-data text-xs">{it.code}</td>
          <td className="px-3">{it.item_name}</td>
          <td className="px-2">{it.unit}</td>
          <td className="text-right px-2 font-mono-data">{it.issued_qty}</td>
          <td className="text-right px-2 font-mono-data">{it.returned_qty || ""}</td>
          <td className="text-right px-2 font-mono-data font-medium">{it.net_qty}</td>
          <td className="text-right px-2 font-mono-data">{it.weight_kg ? it.weight_kg : "—"}</td>
          <td className="text-right px-3 font-mono-data">{inr(it.rate)}</td>
          <td className="text-right px-3 font-mono-data">{inr(it.value)}</td>
        </tr>
      ))}
      <tr className="border-t bg-slate-50/70 font-medium">
        <td colSpan={3} className="px-3 py-1.5 text-xs text-slate-600">Subtotal — {cat.category}</td>
        <td className="text-right px-2 font-mono-data">{cat.total_issued}</td>
        <td></td>
        <td></td>
        <td className="text-right px-2 font-mono-data">{cat.total_weight_kg || ""}</td>
        <td></td>
        <td className="text-right px-3 font-mono-data">{inr(cat.total_value)}</td>
      </tr>
    </>
  );
}
