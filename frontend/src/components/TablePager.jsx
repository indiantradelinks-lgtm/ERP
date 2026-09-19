import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

const SIZES = [25, 50, 100, 200];

export default function TablePager({ pagination, testidPrefix = "tbl" }) {
  const { page, pages, pageSize, total, loading, setPage, setPageSize } = pagination;
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  const btn = "h-7 w-7 p-0 rounded-sm";
  return (
    <div className="flex flex-wrap items-center gap-3" data-testid={`${testidPrefix}-pager`}>
      <span className="text-xs text-muted-foreground" data-testid={`${testidPrefix}-pager-range`}>
        Showing <span className="text-foreground font-semibold">{from}–{to}</span> of <span className="text-foreground font-semibold">{total.toLocaleString("en-IN")}</span>
        {loading && <Loader2 className="inline h-3 w-3 ml-2 animate-spin text-primary" data-testid={`${testidPrefix}-pager-loading`} />}
      </span>
      <div className="flex items-center gap-1 ml-auto">
        <select
          className="h-7 rounded-sm border border-input bg-background px-1.5 text-xs"
          value={pageSize}
          onChange={(e) => setPageSize(Number(e.target.value))}
          data-testid={`${testidPrefix}-page-size`}
          title="Rows per page"
        >
          {SIZES.map((n) => <option key={n} value={n}>{`${n} / page`}</option>)}
        </select>
        <Button size="sm" variant="outline" className={btn} disabled={page <= 1} onClick={() => setPage(1)} data-testid={`${testidPrefix}-page-first`}><ChevronsLeft className="h-3.5 w-3.5" /></Button>
        <Button size="sm" variant="outline" className={btn} disabled={page <= 1} onClick={() => setPage(page - 1)} data-testid={`${testidPrefix}-page-prev`}><ChevronLeft className="h-3.5 w-3.5" /></Button>
        <span className="text-xs px-2 tabular-nums" data-testid={`${testidPrefix}-page-indicator`}>Page {page} / {pages}</span>
        <Button size="sm" variant="outline" className={btn} disabled={page >= pages} onClick={() => setPage(page + 1)} data-testid={`${testidPrefix}-page-next`}><ChevronRight className="h-3.5 w-3.5" /></Button>
        <Button size="sm" variant="outline" className={btn} disabled={page >= pages} onClick={() => setPage(pages)} data-testid={`${testidPrefix}-page-last`}><ChevronsRight className="h-3.5 w-3.5" /></Button>
      </div>
    </div>
  );
}
