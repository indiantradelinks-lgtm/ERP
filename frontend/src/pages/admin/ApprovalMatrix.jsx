import { useEffect, useState } from "react";
import { Plus, Trash2, ChevronUp, ChevronDown, RotateCcw, Workflow } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/DataTableShell";
import { api } from "@/lib/api";
import { toast } from "sonner";

export default function ApprovalMatrix() {
  const [matrix, setMatrix] = useState([]);
  const [roles, setRoles] = useState([]);
  const [drafts, setDrafts] = useState({}); // type -> {steps: [...]}
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const [m, r] = await Promise.all([
        api.get("/admin/approval-matrix"),
        api.get("/admin/approval-matrix/roles"),
      ]);
      setMatrix(m.data);
      setRoles(r.data);
      setDrafts({});
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load matrix");
    }
  };
  useEffect(() => { load(); }, []);

  const draftSteps = (type) => drafts[type] ?? matrix.find((m) => m.type === type)?.steps ?? [];

  const setSteps = (type, steps) => setDrafts((d) => ({ ...d, [type]: steps }));

  const addStep = (type) => {
    const steps = [...draftSteps(type), { role: roles[0] || "dept_head", label: "New step" }];
    setSteps(type, steps);
  };
  const removeStep = (type, idx) => {
    const steps = draftSteps(type).filter((_, i) => i !== idx);
    setSteps(type, steps);
  };
  const moveStep = (type, idx, dir) => {
    const steps = [...draftSteps(type)];
    const j = idx + dir;
    if (j < 0 || j >= steps.length) return;
    [steps[idx], steps[j]] = [steps[j], steps[idx]];
    setSteps(type, steps);
  };
  const updateStep = (type, idx, key, val) => {
    const steps = draftSteps(type).map((s, i) => (i === idx ? { ...s, [key]: val } : s));
    setSteps(type, steps);
  };

  const save = async (type) => {
    setBusy(true);
    try {
      await api.put(`/admin/approval-matrix/${type}`, { type, steps: draftSteps(type) });
      toast.success("Saved");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const reset = async (type) => {
    if (!window.confirm(`Reset "${type}" back to the built-in default chain?`)) return;
    setBusy(true);
    try {
      await api.delete(`/admin/approval-matrix/${type}`);
      toast.success("Reset to default");
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Reset failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="admin-matrix">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5">Super Admin · Workflow</div>
        <h1 className="font-display font-black text-3xl tracking-tight flex items-center gap-2">
          <Workflow className="h-7 w-7 text-primary" /> Approval Matrix
        </h1>
        <p className="text-sm text-muted-foreground mt-1">Define the ordered approver chain for every request type. Reordering or saving creates a DB override; "Reset" reverts to the built-in default.</p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 stagger">
        {matrix.map((chain) => {
          const steps = draftSteps(chain.type);
          const dirty = drafts[chain.type] !== undefined;
          return (
            <div key={chain.type} className="bg-card border border-border rounded-sm" data-testid={`matrix-${chain.type}`}>
              <div className="flex items-center justify-between p-4 border-b border-border">
                <div className="flex items-center gap-2">
                  <div className="font-display font-bold capitalize">{chain.type.replaceAll("_", " ")}</div>
                  <StatusBadge text={chain.source} tone={chain.source === "custom" ? "primary" : "neutral"} />
                  {dirty && <StatusBadge text="unsaved" tone="warning" />}
                </div>
                <div className="flex items-center gap-1">
                  {chain.source === "custom" && (
                    <Button variant="outline" size="sm" className="h-8 rounded-sm" onClick={() => reset(chain.type)} disabled={busy} data-testid={`matrix-${chain.type}-reset`}>
                      <RotateCcw className="h-3.5 w-3.5 mr-1" /> Reset
                    </Button>
                  )}
                  <Button size="sm" className="h-8 rounded-sm" onClick={() => save(chain.type)} disabled={busy || !dirty} data-testid={`matrix-${chain.type}-save`}>Save</Button>
                </div>
              </div>
              <ul className="divide-y divide-border">
                {steps.map((s, i) => (
                  <li key={`${chain.type}-${i}`} className="flex items-center gap-2 p-3" data-testid={`matrix-${chain.type}-step-${i}`}>
                    <span className="h-7 w-7 rounded-sm bg-primary/10 text-primary grid place-items-center text-xs font-bold tabular shrink-0">{i + 1}</span>
                    <select
                      className="h-9 rounded-sm border border-input bg-background px-2 text-sm w-40"
                      value={s.role}
                      onChange={(e) => updateStep(chain.type, i, "role", e.target.value)}
                      data-testid={`matrix-${chain.type}-role-${i}`}
                    >
                      {roles.map((r) => <option key={r} value={r}>{r.replaceAll("_", " ")}</option>)}
                    </select>
                    <input
                      className="h-9 flex-1 rounded-sm border border-input bg-background px-2 text-sm"
                      value={s.label}
                      onChange={(e) => updateStep(chain.type, i, "label", e.target.value)}
                      placeholder="Step label"
                      data-testid={`matrix-${chain.type}-label-${i}`}
                    />
                    <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => moveStep(chain.type, i, -1)} disabled={i === 0} title="Move up"><ChevronUp className="h-3.5 w-3.5" /></Button>
                    <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => moveStep(chain.type, i, 1)} disabled={i === steps.length - 1} title="Move down"><ChevronDown className="h-3.5 w-3.5" /></Button>
                    <Button size="icon" variant="ghost" className="h-7 w-7 text-destructive" onClick={() => removeStep(chain.type, i)} disabled={steps.length <= 1} title="Remove"><Trash2 className="h-3.5 w-3.5" /></Button>
                  </li>
                ))}
              </ul>
              <div className="p-3 border-t border-border">
                <Button variant="outline" size="sm" className="h-8 rounded-sm" onClick={() => addStep(chain.type)} data-testid={`matrix-${chain.type}-add-step`}>
                  <Plus className="h-3.5 w-3.5 mr-1" /> Add step
                </Button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
