import { Link } from "react-router-dom";
import {
  ArrowRight, Shield, Activity, Users2, Boxes, Wallet, BarChart3, CheckCircle2,
  HardHat, ShieldCheck, LineChart, Workflow, Building2
} from "lucide-react";
import Brand from "@/components/Brand";
import { Button } from "@/components/ui/button";

const SERVICES = [
  { name: "Scaffolding", desc: "Multi-level erection, inspection registers, dismantle tracking." },
  { name: "Painting", desc: "Surface prep, batch traceability, coat-by-coat sign-off." },
  { name: "Roof Sheeting", desc: "Panel inventory, fall-arrest permits, install QA." },
  { name: "Rope Access", desc: "Crew certifications, daily LMRA logs, anchor inspections." },
  { name: "Shutdown & Maintenance", desc: "Turnaround scopes, permit chains, daily progress." },
];

const MODULES = [
  { icon: BarChart3, label: "Executive Single-Window" },
  { icon: Users2, label: "Client Management" },
  { icon: Building2, label: "Vendor & Compliance" },
  { icon: HardHat, label: "HRMS & Payroll" },
  { icon: Workflow, label: "Approvals Workflow" },
  { icon: Boxes, label: "Inventory & Stores" },
  { icon: Wallet, label: "Accounts & Cost Centre" },
  { icon: ShieldCheck, label: "Safety & Permits" },
  { icon: LineChart, label: "Reports & Analytics" },
];

export default function Landing() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Nav */}
      <header className="sticky top-0 z-30 backdrop-blur-md bg-background/70 border-b border-border">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <Brand />
          <nav className="hidden md:flex items-center gap-8 text-sm">
            <a href="#services" className="hover-amber text-muted-foreground">Services</a>
            <a href="#modules" className="hover-amber text-muted-foreground">Modules</a>
            <a href="#why" className="hover-amber text-muted-foreground">Why us</a>
          </nav>
          <div className="flex items-center gap-2">
            <Link to="/login">
              <Button variant="outline" className="h-9 rounded-sm border-border" data-testid="landing-signin-btn">Sign in</Button>
            </Link>
            <Link to="/login">
              <Button className="h-9 rounded-sm" data-testid="landing-launch-btn">
                Launch Control Room <ArrowRight className="h-3.5 w-3.5 ml-1" />
              </Button>
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden border-b border-border">
        <div className="absolute inset-0 industrial-gridlines opacity-30" />
        <div className="absolute inset-0 bg-grain" />
        <div className="absolute -top-40 -right-40 w-[600px] h-[600px] rounded-full bg-primary/10 blur-3xl" />
        <div className="relative max-w-7xl mx-auto px-6 py-20 lg:py-28 grid lg:grid-cols-12 gap-10 items-center">
          <div className="lg:col-span-7 stagger">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 border border-border bg-card/70 rounded-sm text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground" data-testid="landing-eyebrow">
              <span className="h-1.5 w-1.5 bg-success rounded-full animate-pulse" />
              Live · Industrial Service Operations
            </div>
            <h1 className="mt-5 font-display font-black text-4xl sm:text-5xl lg:text-6xl tracking-tight leading-[1.05]">
              The single window for <span className="text-primary">industrial</span><br/>
              service operations.
            </h1>
            <p className="mt-5 text-base sm:text-lg text-muted-foreground max-w-2xl leading-relaxed">
              WorkSite Command runs your scaffolding, painting, roof sheeting, rope access and shutdown jobs end-to-end —
              from quote to invoice, permit to payroll, store to safety. Built for service contractors, not generic SaaS.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link to="/login">
                <Button className="h-11 px-5 rounded-sm text-sm font-bold uppercase tracking-wider" data-testid="hero-cta-launch">
                  Launch Control Room <ArrowRight className="h-4 w-4 ml-2" />
                </Button>
              </Link>
              <a href="#modules">
                <Button variant="outline" className="h-11 px-5 rounded-sm border-border text-sm font-bold uppercase tracking-wider" data-testid="hero-cta-modules">
                  Explore Modules
                </Button>
              </a>
            </div>

            <div className="mt-10 grid grid-cols-3 max-w-lg gap-x-6 gap-y-4">
              {[
                { v: "14+", l: "Modules" },
                { v: "60s", l: "Daily DPR" },
                { v: "ISO", l: "45001 Ready" },
              ].map((s) => (
                <div key={s.l} className="border-l-2 border-primary pl-3">
                  <div className="font-display font-black text-2xl tabular leading-none">{s.v}</div>
                  <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground mt-1">{s.l}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="lg:col-span-5 relative">
            <div className="relative rounded-sm border border-border bg-card overflow-hidden shadow-[0_30px_80px_-30px_rgba(245,158,11,0.25)]">
              <img
                src="https://images.unsplash.com/photo-1504964670878-71b73cec0ce1?crop=entropy&cs=srgb&fm=jpg&q=85"
                alt="Industrial scaffolding site"
                className="w-full h-72 object-cover"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-card via-card/30 to-transparent" />
              <div className="absolute bottom-0 left-0 right-0 p-5">
                <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-primary">
                  <Activity className="h-3.5 w-3.5" /> Real-time mission control
                </div>
                <div className="mt-1 font-display font-bold text-lg">Active projects, permits & payroll — one screen.</div>
              </div>
            </div>
            <div className="absolute -bottom-6 -left-6 hidden sm:block bg-card border border-border rounded-sm p-4 w-52 shadow-xl">
              <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Outstanding</div>
              <div className="font-display font-black text-2xl tabular text-success mt-0.5">₹ 4.82Cr</div>
              <div className="text-xs text-muted-foreground mt-0.5">Receivables · Feb</div>
            </div>
          </div>
        </div>
      </section>

      {/* Services */}
      <section id="services" className="border-b border-border">
        <div className="max-w-7xl mx-auto px-6 py-20">
          <div className="flex items-end justify-between flex-wrap gap-4 mb-10">
            <div>
              <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-2">Service Lines</div>
              <h2 className="font-display font-black text-3xl sm:text-4xl tracking-tight">Engineered for the work that pays the bills.</h2>
            </div>
            <p className="max-w-md text-sm text-muted-foreground">Each module respects the rhythm of your trade — permits, crews, scaffolds, ropes, sheets, shutdowns.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
            {SERVICES.map((s, i) => (
              <div key={s.name} className="border border-border rounded-sm p-5 bg-card hover:border-primary/50 transition-colors duration-200">
                <div className="font-display font-bold text-xs uppercase tracking-[0.12em] text-primary">{String(i + 1).padStart(2, "0")}</div>
                <div className="mt-2 font-display font-bold text-base">{s.name}</div>
                <div className="text-xs text-muted-foreground mt-2 leading-relaxed">{s.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Modules */}
      <section id="modules" className="border-b border-border bg-muted/30">
        <div className="max-w-7xl mx-auto px-6 py-20">
          <div className="grid md:grid-cols-3 gap-10 items-start">
            <div className="md:col-span-1">
              <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-2">Modules</div>
              <h2 className="font-display font-black text-3xl sm:text-4xl tracking-tight">One platform. Every department.</h2>
              <p className="mt-4 text-sm text-muted-foreground leading-relaxed">
                From safety officer mobile uploads to director-level P&L drill-downs — every workflow connects.
              </p>
            </div>
            <div className="md:col-span-2 grid grid-cols-2 lg:grid-cols-3 gap-px bg-border rounded-sm overflow-hidden">
              {MODULES.map((m) => (
                <div key={m.label} className="bg-card p-5 flex items-center gap-3 hover:bg-muted/40 transition-colors duration-200">
                  <div className="h-9 w-9 grid place-items-center bg-primary/10 text-primary rounded-sm border border-primary/20">
                    <m.icon className="h-4 w-4" />
                  </div>
                  <div className="text-sm font-semibold">{m.label}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Why */}
      <section id="why" className="border-b border-border">
        <div className="max-w-7xl mx-auto px-6 py-20 grid lg:grid-cols-2 gap-10 items-center">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-2">Why WorkSite</div>
            <h2 className="font-display font-black text-3xl sm:text-4xl tracking-tight">Built like SAP. Used like a clipboard.</h2>
            <ul className="mt-6 space-y-3">
              {[
                "Role-based hierarchy with multi-level approvals — director to supervisor.",
                "Cost-centre P&L by project, site, vehicle, crew or asset.",
                "Mobile-first safety reports with photo upload & geo-tag.",
                "Audit log on every record. Exportable to PDF and Excel.",
              ].map((x) => (
                <li key={x} className="flex items-start gap-3 text-sm">
                  <CheckCircle2 className="h-4 w-4 mt-0.5 text-primary shrink-0" /> {x}
                </li>
              ))}
            </ul>
          </div>
          <div className="bg-secondary text-secondary-foreground rounded-sm p-8 relative overflow-hidden">
            <div className="absolute inset-0 industrial-gridlines opacity-10" />
            <div className="relative">
              <Shield className="h-8 w-8 text-primary" />
              <div className="mt-4 font-display font-black text-2xl">Audit-ready by design.</div>
              <p className="mt-2 text-sm text-secondary-foreground/70">Every approval, edit and signature is timestamped. Built for industrial clients that demand traceability.</p>
              <Link to="/login">
                <Button className="mt-6 rounded-sm" data-testid="why-cta-launch">Launch Control Room</Button>
              </Link>
            </div>
          </div>
        </div>
      </section>

      <footer className="border-t border-border">
        <div className="max-w-7xl mx-auto px-6 py-8 flex flex-wrap items-center justify-between gap-4">
          <Brand />
          <div className="text-xs text-muted-foreground">© {new Date().getFullYear()} WorkSite Command — Industrial Service ERP.</div>
        </div>
      </footer>
    </div>
  );
}
