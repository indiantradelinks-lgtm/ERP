import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { ShieldAlert, RefreshCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const TONE = (v) => {
  if (v === 0 || v === "0") return "neutral";
  if (typeof v === "number" && v > 0) return "warn";
  return "neutral";
};

export default function SafetyDashboard() {
  const [data, setData] = useState(null);
  const navigate = useNavigate();

  const load = async () => {
    try {
      const r = await api.get("/safety/dashboard");
      setData(r.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Failed to load safety dashboard"); }
  };
  useEffect(() => { load(); }, []);

  if (!data) return <div className="p-6 text-sm text-muted-foreground">Loading safety dashboard…</div>;

  return (
    <div className="p-6 space-y-5" data-testid="safety-dashboard-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-red-700 mb-1.5">Module · Safety</div>
          <h1 className="font-display font-black text-3xl tracking-tight flex items-center gap-2">
            <ShieldAlert className="h-7 w-7 text-red-600" /> Safety Dashboard
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Real-time HSE indicators — sourced from live records, click any tile to drill down.
          </p>
        </div>
        <Button variant="outline" onClick={load} data-testid="safety-dash-refresh">
          <RefreshCcw className="h-3.5 w-3.5 mr-1.5" /> Refresh
        </Button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
        {data.cards.map((c) => (
          <button
            key={c.key}
            type="button"
            disabled={!c.deeplink}
            onClick={() => c.deeplink && navigate(c.deeplink)}
            className={cn(
              "bg-card border rounded-sm p-3 text-left transition-colors",
              c.deeplink ? "hover:border-red-400 hover:bg-red-50/40 cursor-pointer" : "cursor-default",
              TONE(c.value) === "warn" && c.value > 0 ? "border-red-200" : "border-border",
            )}
            data-testid={`safety-card-${c.key}`}
          >
            <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground leading-tight">
              {c.label}
            </div>
            <div className={cn(
              "font-display font-black text-3xl tabular leading-none mt-1.5",
              c.value > 0 ? "text-red-700" : "text-muted-foreground",
            )}>
              {c.value}
            </div>
          </button>
        ))}
      </div>
      <div className="text-[10px] text-muted-foreground">As of {new Date(data.as_of).toLocaleString()}</div>
    </div>
  );
}
