import { useEffect, useState } from "react";
import { Trophy, ChevronLeft, ChevronRight, Medal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

const shiftMonth = (ym, delta) => {
  const [y, m] = ym.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + delta, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
};
const thisMonth = () => new Date().toISOString().slice(0, 7);
const monthLabel = (ym) => new Date(`${ym}-01T00:00:00Z`).toLocaleDateString("en-IN", { month: "long", year: "numeric", timeZone: "UTC" });
const inr = (n) => "₹" + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });
const RANK_TONE = ["text-amber-500", "text-slate-400", "text-orange-700"];

/** Per sales-user monthly tile: enquiries raised, quotes sent, won/lost and win rate. */
export default function SalesLeaderboard() {
  const [month, setMonth] = useState(thisMonth());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.get(`/sales/leaderboard?month=${month}`)
      .then((r) => { if (alive) setData(r.data); })
      .catch(() => { if (alive) setData(null); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [month]);

  const rows = data?.rows || [];
  const t = data?.totals || {};
  return (
    <div className="bg-card border border-border rounded-sm" data-testid="sales-leaderboard">
      <div className="flex flex-wrap items-center gap-3 px-5 py-3 border-b border-border">
        <Trophy className="h-4 w-4 text-primary" />
        <h2 className="font-display font-bold text-base md:text-lg tracking-tight">Sales Leaderboard</h2>
        <span className="text-xs text-muted-foreground hidden md:inline">Enquiries raised · quotes sent · win rate (won ÷ decided) — sales roles only</span>
        <div className="ml-auto flex items-center gap-1">
          <Button size="icon" variant="outline" className="h-7 w-7 rounded-sm" onClick={() => setMonth(shiftMonth(month, -1))} data-testid="leaderboard-prev-month"><ChevronLeft className="h-3.5 w-3.5" /></Button>
          <span className="text-xs font-semibold tabular-nums min-w-[120px] text-center" data-testid="leaderboard-month">{monthLabel(month)}</span>
          <Button size="icon" variant="outline" className="h-7 w-7 rounded-sm" disabled={month >= thisMonth()} onClick={() => setMonth(shiftMonth(month, 1))} data-testid="leaderboard-next-month"><ChevronRight className="h-3.5 w-3.5" /></Button>
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 divide-x divide-border border-b border-border text-center">
        {[["Enquiries", t.enquiries], ["Quotes Sent", t.quotes], ["Won / Lost", `${t.won ?? 0} / ${t.lost ?? 0}`], ["Team Win Rate", t.win_rate == null ? "—" : `${t.win_rate}%`]].map(([l, v]) => (
          <div key={l} className="py-2.5" data-testid={`leaderboard-total-${l.toLowerCase().replace(/[^a-z]+/g, "-")}`}>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{l}</div>
            <div className="font-display font-bold text-lg tabular-nums">{loading ? "…" : (v ?? 0)}</div>
          </div>
        ))}
      </div>
      {!loading && rows.length === 0 && <div className="px-5 py-6 text-sm text-muted-foreground" data-testid="leaderboard-empty">No users with a sales role yet — add one in Admin → Users to start ranking.</div>}
      {rows.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 p-4">
          {rows.map((r) => (
            <div key={r.user_id} className="border border-border rounded-sm p-3 flex gap-3 items-start hover:border-primary/40 transition-colors" data-testid={`leaderboard-user-${r.user_id}`}>
              <div className={`flex flex-col items-center w-8 shrink-0 ${RANK_TONE[r.rank - 1] || "text-muted-foreground"}`}>
                <Medal className="h-5 w-5" />
                <span className="text-[10px] font-bold">#{r.rank}</span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-sm truncate">{r.name}</div>
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{(r.role || "").replaceAll("_", " ")}</div>
                <div className="grid grid-cols-3 gap-2 mt-2 text-center">
                  <div><div className="text-base font-bold tabular-nums" data-testid={`lb-enq-${r.user_id}`}>{r.enquiries}</div><div className="text-[10px] text-muted-foreground">Enquiries</div></div>
                  <div><div className="text-base font-bold tabular-nums" data-testid={`lb-quotes-${r.user_id}`}>{r.quotes}</div><div className="text-[10px] text-muted-foreground">Quotes</div></div>
                  <div><div className={`text-base font-bold tabular-nums ${r.win_rate == null ? "text-muted-foreground" : r.win_rate >= 50 ? "text-success" : "text-warning"}`} data-testid={`lb-winrate-${r.user_id}`}>{r.win_rate == null ? "—" : `${r.win_rate}%`}</div><div className="text-[10px] text-muted-foreground">Win rate</div></div>
                </div>
                <div className="mt-1.5 text-[11px] text-muted-foreground flex justify-between">
                  <span>Won {r.won} · Lost {r.lost}</span>
                  <span title="Value of quotes sent">{inr(r.quote_value)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
