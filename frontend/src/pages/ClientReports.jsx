import { useEffect, useState } from "react";
import { Building2, MapPin, Receipt, Users, BarChart3, Globe2, History } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { StatusBadge } from "@/components/DataTableShell";
import { api } from "@/lib/api";

const TABS = [
  { id: "by-client", label: "By Client", icon: Building2 },
  { id: "by-site", label: "By Site", icon: MapPin },
  { id: "by-gst", label: "By GST", icon: Receipt },
  { id: "outstanding", label: "Outstanding", icon: Receipt },
  { id: "by-location", label: "By Location", icon: Globe2 },
  { id: "contact-directory", label: "Contact Directory", icon: Users },
  { id: "activity-history", label: "Activity History", icon: History },
];

const inr = (n) => "₹ " + Number(n || 0).toLocaleString("en-IN");

// Map our short tab id → backend endpoint path.
const ENDPOINT_FOR = {
  "by-client": "by-client",
  "by-site": "by-site",
  "by-gst": "by-gst",
  "outstanding": "outstanding-by-site",
  "by-location": "by-location",
  "contact-directory": "contact-directory",
  "activity-history": "activity-history",
};

export default function ClientReports() {
  const [active, setActive] = useState("by-client");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true); setData(null);
    api.get(`/clients/reports/${ENDPOINT_FOR[active]}`)
      .then((r) => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [active]);

  return (
    <div className="space-y-6" data-testid="client-reports">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <BarChart3 className="h-3 w-3" /> Sales · Customer Analytics
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Client Reports</h1>
        <p className="text-sm text-muted-foreground mt-1">Revenue, outstanding, contact directory and activity by client / site.</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <Button
              key={t.id}
              variant={active === t.id ? "default" : "outline"}
              className="rounded-sm h-9"
              onClick={() => setActive(t.id)}
              data-testid={`creport-tab-${t.id}`}
            >
              <Icon className="h-3.5 w-3.5 mr-1.5" /> {t.label}
            </Button>
          );
        })}
      </div>

      <div className="bg-card border border-border rounded-sm p-5 min-h-[200px]" data-testid={`creport-pane-${active}`}>
        {loading && <div className="text-sm text-muted-foreground">Loading…</div>}
        {!loading && data && active === "by-client" && <ByClientTable rows={data} />}
        {!loading && data && active === "by-site" && <BySiteTable rows={data} />}
        {!loading && data && active === "by-gst" && <ByGstTable rows={data} />}
        {!loading && data && active === "outstanding" && <OutstandingTable rows={data} />}
        {!loading && data && active === "by-location" && <ByLocationTable rows={data} />}
        {!loading && data && active === "contact-directory" && <ContactDirectoryTable rows={data} />}
        {!loading && data && active === "activity-history" && <ActivityTable rows={data} />}
        {!loading && (!data || (Array.isArray(data) && data.length === 0)) && <div className="text-sm text-muted-foreground text-center py-8">No data yet.</div>}
      </div>
    </div>
  );
}

function ByClientTable({ rows }) {
  return (
    <Table>
      <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
        <TableHead className="text-[10px] uppercase tracking-wider">Code</TableHead>
        <TableHead className="text-[10px] uppercase tracking-wider">Client</TableHead>
        <TableHead className="text-[10px] uppercase tracking-wider">Quote Value</TableHead>
        <TableHead className="text-[10px] uppercase tracking-wider">Order Value</TableHead>
        <TableHead className="text-[10px] uppercase tracking-wider"># Deals</TableHead>
      </TableRow></TableHeader>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.client_id} className="hover:bg-muted/30" data-testid={`creport-row-${r.client_id}`}>
            <TableCell className="font-mono-data text-xs">{r.customer_code}</TableCell>
            <TableCell className="text-sm font-semibold">{r.client_name}</TableCell>
            <TableCell className="text-sm tabular">{inr(r.quotation_amount)}</TableCell>
            <TableCell className="text-sm tabular">{inr(r.order_amount)}</TableCell>
            <TableCell className="text-sm tabular">{r.deal_count}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function BySiteTable({ rows }) {
  return (
    <Table>
      <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
        <TableHead className="text-[10px] uppercase tracking-wider">Site Code</TableHead>
        <TableHead className="text-[10px] uppercase tracking-wider">Client / Site</TableHead>
        <TableHead className="text-[10px] uppercase tracking-wider">Location</TableHead>
        <TableHead className="text-[10px] uppercase tracking-wider">Quote</TableHead>
        <TableHead className="text-[10px] uppercase tracking-wider">Order</TableHead>
      </TableRow></TableHeader>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.site_id} className="hover:bg-muted/30">
            <TableCell className="font-mono-data text-xs">{r.site_code}</TableCell>
            <TableCell className="text-sm font-semibold">{r.client_name} · {r.site_name}</TableCell>
            <TableCell className="text-sm">{r.city}, {r.state}</TableCell>
            <TableCell className="text-sm tabular">{inr(r.quotation_amount)}</TableCell>
            <TableCell className="text-sm tabular">{inr(r.order_amount)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function ByGstTable({ rows }) {
  return (
    <ul className="space-y-3">
      {rows.map((r) => (
        <li key={r.gst} className="border border-border rounded-sm p-3 bg-muted/20">
          <div className="flex items-center justify-between mb-2">
            <div>
              <span className="font-mono-data text-xs bg-primary/10 text-primary px-1.5 py-0.5 rounded-sm font-bold">{r.gst}</span>
              <span className="ml-2 text-sm font-semibold">{r.state}</span>
            </div>
            <StatusBadge text={`${r.sites.length} site${r.sites.length !== 1 ? "s" : ""}`} tone="info" />
          </div>
          <ul className="text-xs text-muted-foreground space-y-0.5 pl-2">
            {r.sites.map((s) => <li key={s.site_code}>· <span className="font-mono-data text-foreground">{s.site_code}</span> — {s.client_name} ({s.name})</li>)}
          </ul>
        </li>
      ))}
    </ul>
  );
}

function OutstandingTable({ rows }) {
  return (
    <Table>
      <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
        <TableHead className="text-[10px] uppercase tracking-wider">Site</TableHead>
        <TableHead className="text-[10px] uppercase tracking-wider">Client</TableHead>
        <TableHead className="text-[10px] uppercase tracking-wider">City</TableHead>
        <TableHead className="text-[10px] uppercase tracking-wider">Invoices</TableHead>
        <TableHead className="text-[10px] uppercase tracking-wider">Outstanding</TableHead>
      </TableRow></TableHeader>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.site_id} className="hover:bg-muted/30">
            <TableCell className="font-mono-data text-xs">{r.site_code}</TableCell>
            <TableCell className="text-sm font-semibold">{r.client_name}</TableCell>
            <TableCell className="text-sm">{r.city}</TableCell>
            <TableCell className="text-sm tabular">{r.invoice_count}</TableCell>
            <TableCell className="text-sm tabular text-destructive font-bold">{inr(r.outstanding)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function ByLocationTable({ rows }) {
  const max = rows.reduce((m, r) => Math.max(m, r.count), 1);
  return (
    <ul className="space-y-2">
      {rows.map((r, idx) => (
        <li key={`${r.state}-${r.city}-${idx}`}>
          <div className="flex items-center justify-between text-sm mb-1">
            <span className="font-semibold">{r.state} · {r.city}</span>
            <span className="font-display font-bold tabular">{r.count}</span>
          </div>
          <div className="h-1.5 rounded-full bg-muted overflow-hidden">
            <div className="h-full bg-primary" style={{ width: `${(r.count / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function ContactDirectoryTable({ rows }) {
  return (
    <Table>
      <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
        <TableHead className="text-[10px] uppercase tracking-wider">Name</TableHead>
        <TableHead className="text-[10px] uppercase tracking-wider">Designation</TableHead>
        <TableHead className="text-[10px] uppercase tracking-wider">Dept</TableHead>
        <TableHead className="text-[10px] uppercase tracking-wider">Site</TableHead>
        <TableHead className="text-[10px] uppercase tracking-wider">Mobile</TableHead>
        <TableHead className="text-[10px] uppercase tracking-wider">Email</TableHead>
      </TableRow></TableHeader>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.id} className="hover:bg-muted/30">
            <TableCell className="text-sm font-semibold">{r.name}</TableCell>
            <TableCell className="text-sm">{r.designation || "—"}</TableCell>
            <TableCell><StatusBadge text={r.department || "—"} tone="info" /></TableCell>
            <TableCell className="text-xs"><span className="font-mono-data">{r.site_code}</span> · {r.client_name}</TableCell>
            <TableCell className="font-mono-data text-xs">{r.mobile || "—"}</TableCell>
            <TableCell className="text-xs">{r.email || "—"}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function ActivityTable({ rows }) {
  return (
    <Table>
      <TableHeader><TableRow className="bg-muted/40 hover:bg-muted/40">
        <TableHead className="text-[10px] uppercase tracking-wider">When</TableHead>
        <TableHead className="text-[10px] uppercase tracking-wider">Action</TableHead>
        <TableHead className="text-[10px] uppercase tracking-wider">Actor</TableHead>
        <TableHead className="text-[10px] uppercase tracking-wider">Record</TableHead>
      </TableRow></TableHeader>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.id} className="hover:bg-muted/30">
            <TableCell className="font-mono-data text-xs">{(r.at || "").slice(0, 16).replace("T", " ")}</TableCell>
            <TableCell><StatusBadge text={r.action} tone="info" /></TableCell>
            <TableCell className="text-sm">{r.user_name || r.user_email || "—"}</TableCell>
            <TableCell className="font-mono-data text-xs">{r.record_id?.slice(0, 8)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
