import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";
import { CheckCircle2, Loader2, FileText } from "lucide-react";
import Brand from "@/components/Brand";

const inr = (n) => "₹ " + Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function PoAck() {
  const { token } = useParams();
  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get(`/public/po-ack/${token}`)
      .then((r) => setInfo(r.data))
      .catch((e) => setError(apiErrorMessage(e, "Invalid or expired link")));
  }, [token]);

  const acknowledge = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/public/po-ack/${token}`, { name: name.trim() || undefined });
      setInfo((i) => ({ ...i, acknowledged_at: data.acknowledged_at, acknowledged_by: data.acknowledged_by }));
      toast.success(`PO ${data.po_number} acknowledged. Thank you!`);
    } catch (e) {
      toast.error(apiErrorMessage(e, "Failed to acknowledge"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex flex-col items-center p-6" data-testid="po-ack-page">
      <div className="w-full max-w-2xl">
        <div className="mb-8"><Brand /></div>
        {error && <div className="border border-red-200 bg-red-50 text-red-700 rounded-sm p-6 text-sm" data-testid="po-ack-error">{error}</div>}
        {!error && !info && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading purchase order…</div>}
        {info && (
          <div className="border rounded-sm bg-card p-6 space-y-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground flex items-center gap-1"><FileText className="h-3 w-3" /> Purchase Order Acknowledgement</div>
                <h1 className="font-display font-black text-2xl mt-1" data-testid="po-ack-number">
                  {info.po_number}{info.revision > 0 && <span className="ml-2 text-xs bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded-sm align-middle">Rev {info.revision}</span>}
                </h1>
                <div className="text-sm text-muted-foreground mt-1">{info.vendor} · {info.date}{info.project ? ` · ${info.project}` : ""}</div>
              </div>
              <div className="text-right">
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Order Value</div>
                <div className="font-display font-black text-xl" data-testid="po-ack-total">{inr(info.total)}</div>
              </div>
            </div>

            {(info.items || []).length > 0 && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                    <th className="py-1.5 pr-2">Item</th><th className="py-1.5 pr-2 text-right">Qty</th>
                    <th className="py-1.5 pr-2 text-right">Rate</th><th className="py-1.5 text-right">Total (incl. GST)</th>
                  </tr>
                </thead>
                <tbody>
                  {info.items.map((it, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className="py-1.5 pr-2 font-medium">{it.name}</td>
                      <td className="py-1.5 pr-2 text-right">{Number(it.quantity || 0).toLocaleString("en-IN")} {it.unit || ""}</td>
                      <td className="py-1.5 pr-2 text-right">{inr(it.rate)}</td>
                      <td className="py-1.5 text-right">{inr(it.line_total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {info.delivery_terms && <div className="text-xs text-muted-foreground"><b>Delivery Terms:</b> {info.delivery_terms}</div>}

            {info.acknowledged_at ? (
              <div className="border border-emerald-200 bg-emerald-50 rounded-sm p-4 flex items-center gap-3" data-testid="po-ack-done">
                <CheckCircle2 className="h-6 w-6 text-emerald-600 shrink-0" />
                <div className="text-sm">
                  <div className="font-semibold text-emerald-800">Purchase Order Acknowledged</div>
                  <div className="text-emerald-700">By {info.acknowledged_by} on {String(info.acknowledged_at).slice(0, 10)}. No further action needed.</div>
                </div>
              </div>
            ) : (
              <div className="border rounded-sm p-4 space-y-3 bg-muted/30">
                <div className="text-sm font-medium">Confirm receipt & acceptance of this Purchase Order</div>
                <Input placeholder="Your name (optional)" value={name} onChange={(e) => setName(e.target.value)} className="rounded-sm max-w-xs" data-testid="po-ack-name-input" />
                <Button onClick={acknowledge} disabled={busy} className="rounded-sm" data-testid="po-ack-btn">
                  {busy ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <CheckCircle2 className="h-4 w-4 mr-2" />} Acknowledge PO
                </Button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
