/**
 * Rate Contract Hint
 *
 * Small inline component that surfaces active rate contracts matching the
 * given item (by item_id or item_name). Used in the PR creation dialog to
 * auto-suggest a vendor + locked rate.
 *
 * Backend: GET /api/procurement-extras/rate-contracts/suggest
 */
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Sparkles, CheckCircle2, X } from "lucide-react";

const DEBOUNCE_MS = 350;

export default function RateContractHint({ itemId, itemName, onApply }) {
  const [match, setMatch] = useState(null);
  const [loading, setLoading] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const lastKeyRef = useRef("");

  useEffect(() => {
    const key = itemId ? `id:${itemId}` : (itemName || "").trim().toLowerCase();
    if (!key || key.length < 3) { setMatch(null); return; }
    if (key === lastKeyRef.current) return;
    lastKeyRef.current = key;
    setDismissed(false);

    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const params = itemId ? { item_id: itemId } : { item_name: itemName };
        const { data } = await api.get("/procurement-extras/rate-contracts/suggest", { params });
        const top = (data?.matches || [])[0] || null;
        setMatch(top);
      } catch {
        setMatch(null);
      } finally {
        setLoading(false);
      }
    }, DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [itemId, itemName]);

  if (dismissed || !match) return null;

  return (
    <div className="mt-1 inline-flex items-center gap-2 rounded-sm border border-emerald-300 bg-emerald-50 px-2 py-1 text-[11px]" data-testid="rc-hint">
      <Sparkles className="h-3 w-3 text-emerald-700 shrink-0" />
      <span className="text-emerald-800">
        Active rate contract · <b>₹{Number(match.rate).toLocaleString("en-IN")} / {match.unit}</b> from <b>{match.vendor_name}</b>
        {match.end_date && <> · exp <span className="font-mono">{match.end_date}</span></>}
      </span>
      <button
        type="button"
        className="ml-1 px-1.5 py-0.5 rounded-sm bg-emerald-700 text-white text-[10px] hover:bg-emerald-800 inline-flex items-center gap-1"
        onClick={() => { onApply?.(match); setDismissed(true); }}
        data-testid="rc-hint-apply"
        title="Auto-fill vendor and unit from this rate contract"
      >
        <CheckCircle2 className="h-3 w-3" /> Apply
      </button>
      <button
        type="button"
        className="text-emerald-700 hover:text-emerald-900"
        onClick={() => setDismissed(true)}
        data-testid="rc-hint-dismiss"
        title="Dismiss"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}
