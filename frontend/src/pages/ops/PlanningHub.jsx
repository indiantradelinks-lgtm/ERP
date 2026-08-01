import { useSearchParams } from "react-router-dom";
import { ClipboardList } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/contexts/AuthContext";
import ProjectBOQ from "./ProjectBOQ";
import ProjectWBS from "./ProjectWBS";
import ProjectActivities from "./ProjectActivities";
import ProjectResources from "./ProjectResources";
import ProjectPlanning from "./ProjectPlanning";
import BudgetCommitmentCenter from "@/pages/accounts/BudgetCommitmentCenter";

const TABS = [
  { key: "boq", label: "BOQ / Scope", Comp: ProjectBOQ },
  { key: "wbs", label: "WBS", Comp: ProjectWBS },
  { key: "schedule", label: "Activity Schedule", Comp: ProjectActivities },
  { key: "resources", label: "Resource Planning", Comp: ProjectResources },
  { key: "budget", label: "Project Budget", Comp: BudgetCommitmentCenter, perm: "accounting" },
  { key: "premob", label: "Pre-Mobilization", Comp: ProjectPlanning },
];

export default function PlanningHub() {
  const { can } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabs = TABS.filter((t) => !t.perm || (can ? can(t.perm, "read") : true));
  const requested = searchParams.get("tab");
  const tab = tabs.some((t) => t.key === requested) ? requested : tabs[0]?.key;

  return (
    <div className="space-y-4" data-testid="planning-hub-page">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <ClipboardList className="h-3 w-3" /> Planning Workspace
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Project Planning</h1>
        <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
          BOQ, WBS, schedule, resources, budget and pre-mobilization — one workspace, tab per section.
        </p>
      </div>
      <Tabs value={tab} onValueChange={(v) => setSearchParams({ tab: v })}>
        <TabsList className="rounded-sm flex-wrap h-auto">
          {tabs.map((t) => (
            <TabsTrigger key={t.key} value={t.key} className="rounded-sm" data-testid={`plan-tab-${t.key}`}>{t.label}</TabsTrigger>
          ))}
        </TabsList>
        {tabs.map((t) => (
          <TabsContent key={t.key} value={t.key} className="mt-4">
            {tab === t.key && <t.Comp />}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
