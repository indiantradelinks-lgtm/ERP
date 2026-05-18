import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, CheckCircle2, ChevronRight, Inbox } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { api } from "@/lib/api";

export default function MyApprovalsInbox() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/approvals/inbox/mine");
      setItems(Array.isArray(data) ? data : []);
    } catch (e) {
      setItems([]);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30_000); // poll every 30s
    return () => clearInterval(t);
  }, [load]);

  const count = items.length;

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative h-9 w-9 rounded-sm border border-border hover:border-primary/60"
          data-testid="my-approvals-btn"
          title={`${count} approval${count === 1 ? "" : "s"} waiting on you`}
        >
          <Bell className="h-4 w-4" />
          {count > 0 && (
            <span className="absolute -top-1 -right-1 h-4 min-w-[16px] px-1 grid place-items-center bg-primary text-primary-foreground rounded-full text-[10px] font-bold leading-none">
              {count > 9 ? "9+" : count}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-96 rounded-sm p-0" data-testid="my-approvals-menu">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <div>
            <div className="font-display font-bold text-sm">My Approvals</div>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Waiting on your action</div>
          </div>
          <span className="inline-flex items-center justify-center px-2 py-0.5 text-[10px] font-bold border border-primary/40 bg-primary/10 text-primary rounded-sm">{count}</span>
        </div>
        <div className="max-h-80 overflow-y-auto">
          {loading ? (
            <div className="p-6 text-center text-xs text-muted-foreground">Loading…</div>
          ) : count === 0 ? (
            <div className="p-8 text-center">
              <Inbox className="h-8 w-8 mx-auto text-muted-foreground/40" />
              <div className="mt-3 text-sm font-semibold">Inbox zero</div>
              <div className="text-xs text-muted-foreground mt-1">No approvals waiting on you right now.</div>
            </div>
          ) : (
            <ul className="divide-y divide-border">
              {items.map((a) => {
                const step = a._my_step || (a.chain || [])[a.current_step] || {};
                return (
                  <li
                    key={a.id}
                    className="px-4 py-3 hover:bg-muted/40 cursor-pointer flex items-center gap-3"
                    onClick={() => { setOpen(false); navigate(`/app/approvals?id=${a.id}`); }}
                    data-testid={`my-approval-${a.id}`}
                  >
                    <div className="h-8 w-8 grid place-items-center bg-primary/10 text-primary border border-primary/30 rounded-sm shrink-0">
                      <CheckCircle2 className="h-4 w-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-semibold truncate">{a.title}</div>
                      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                        Step {(a.current_step ?? 0) + 1}/{(a.chain || []).length} · {step.label || "—"}
                        {a.amount ? ` · ₹ ${Number(a.amount).toLocaleString("en-IN")}` : ""}
                      </div>
                    </div>
                    <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        <div className="px-4 py-2 border-t border-border">
          <Button variant="ghost" size="sm" className="w-full rounded-sm text-xs" onClick={() => { setOpen(false); navigate("/app/approvals"); }} data-testid="my-approvals-open-all">
            Open all approvals →
          </Button>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
