/**
 * Mobile-first DPR capture page.
 *  - Single-column, large-touch-target layout for phones.
 *  - Native camera input via <input capture="environment"> for site photos.
 *  - Geolocation stamp on submit.
 *  - Offline queue: if `navigator.onLine` is false OR the API call fails, the
 *    DPR is queued in localStorage and auto-retried when connectivity returns.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Camera, MapPin, Send, WifiOff, CheckCircle2, RotateCcw, X, ChevronLeft, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { toast } from "sonner";

const SERVICE_OPTIONS = ["scaffolding", "painting", "rope_access", "insulation", "roof_sheeting", "combined"];
const SITE_ROLES = ["scaffolder", "painter", "rope_access_tech", "insulation_fitter", "roof_sheeting_worker", "helper", "supervisor", "safety_officer"];
const QUEUE_KEY = "dpr_offline_queue_v1";

const blankForm = () => ({
  date: new Date().toISOString().slice(0, 10),
  project_code: "", site_name: "", service_type: "scaffolding",
  manpower: SITE_ROLES.slice(0, 4).map((r) => ({ role: r, count: 0 })),
  work_completed: "", safety_observations: "",
  client_instructions: "", delay_reasons: "", extra_work: "",
  supervisor_remarks: "",
  photos: [],          // [{ name, dataUrl }]
  gps: null,           // { latitude, longitude, accuracy, timestamp }
});

const readQueue = () => { try { return JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]"); } catch { return []; } };
const writeQueue = (rows) => localStorage.setItem(QUEUE_KEY, JSON.stringify(rows));

const fileToDataUrl = (f) => new Promise((res, rej) => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.onerror = rej; fr.readAsDataURL(f); });

export default function DprMobile() {
  const navigate = useNavigate();
  const [form, setForm] = useState(blankForm());
  const [online, setOnline] = useState(typeof navigator !== "undefined" ? navigator.onLine : true);
  const [pending, setPending] = useState(readQueue().length);
  const [submitting, setSubmitting] = useState(false);
  const [gpsState, setGpsState] = useState("idle");      // idle | locating | ok | denied | error
  const [stepDone, setStepDone] = useState(null);
  const cameraRef = useRef(null);

  // Online/offline + auto-retry queue
  useEffect(() => {
    const onUp = () => { setOnline(true); flushQueue(); };
    const onDown = () => setOnline(false);
    window.addEventListener("online", onUp);
    window.addEventListener("offline", onDown);
    // Try once on mount in case we're already online with a backlog
    if (navigator.onLine) flushQueue();
    return () => { window.removeEventListener("online", onUp); window.removeEventListener("offline", onDown); };
    /* eslint-disable-next-line */
  }, []);

  const flushQueue = async () => {
    const queue = readQueue();
    if (!queue.length) { setPending(0); return; }
    const remaining = [];
    let sent = 0;
    for (const item of queue) {
      try {
        await api.post("/dprs", item);
        sent += 1;
      } catch {
        remaining.push(item);
      }
    }
    writeQueue(remaining);
    setPending(remaining.length);
    if (sent) toast.success(`Synced ${sent} queued DPR${sent === 1 ? "" : "s"}`);
  };

  const captureGps = () => {
    if (!("geolocation" in navigator)) { setGpsState("error"); toast.error("Geolocation not supported"); return; }
    setGpsState("locating");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const gps = {
          latitude: pos.coords.latitude, longitude: pos.coords.longitude,
          accuracy_m: Math.round(pos.coords.accuracy || 0),
          captured_at: new Date(pos.timestamp).toISOString(),
        };
        setForm((f) => ({ ...f, gps }));
        setGpsState("ok");
      },
      (err) => { setGpsState(err.code === 1 ? "denied" : "error"); toast.error(`GPS: ${err.message}`); },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
  };

  const addPhotos = async (files) => {
    if (!files?.length) return;
    const next = [...form.photos];
    for (const f of Array.from(files)) {
      try {
        const dataUrl = await fileToDataUrl(f);
        next.push({ name: f.name || `site-${Date.now()}.jpg`, dataUrl, size: f.size });
      } catch { /* ignore */ }
    }
    setForm({ ...form, photos: next });
  };

  const totalMen = useMemo(() => form.manpower.reduce((a, m) => a + Number(m.count || 0), 0), [form.manpower]);

  const submit = async (submitFlag) => {
    if (!form.project_code.trim()) { toast.error("Project code is required"); return; }
    if (totalMen === 0) { toast.error("Add at least one manpower entry"); return; }
    setSubmitting(true);
    const payload = {
      date: form.date, project_code: form.project_code.trim(), site_name: form.site_name.trim() || null,
      service_type: form.service_type,
      manpower: form.manpower.filter((m) => Number(m.count) > 0).map((m) => ({ role: m.role, count: Number(m.count) })),
      work_completed: form.work_completed,
      safety_observations: form.safety_observations,
      client_instructions: form.client_instructions,
      delay_reasons: form.delay_reasons,
      extra_work: form.extra_work,
      supervisor_remarks: form.supervisor_remarks
        + (form.gps ? `\n\n[GPS] ${form.gps.latitude.toFixed(5)}, ${form.gps.longitude.toFixed(5)} · ±${form.gps.accuracy_m}m · ${form.gps.captured_at}` : ""),
      // Photos are inlined as base64 dataUrls in supervisor_remarks for now to
      // avoid a separate upload pipeline — the server can be augmented to split
      // them out later. For weight reasons we cap the count at 6 photos / DPR.
      site_photos: form.photos.slice(0, 6).map((p) => p.dataUrl),
      submit: submitFlag,
    };
    if (!navigator.onLine) {
      const queue = readQueue(); queue.push(payload); writeQueue(queue);
      setPending(queue.length);
      toast.success("Offline — DPR queued. Will sync when connectivity returns.");
      setStepDone("queued"); setForm(blankForm()); setSubmitting(false);
      return;
    }
    try {
      const { data } = await api.post("/dprs", payload);
      toast.success(`${data.dpr_number} ${data.status === "submitted" ? "submitted" : "saved as draft"}`);
      setStepDone("ok"); setForm(blankForm());
    } catch (e) {
      // API failed — queue it and signal user
      const queue = readQueue(); queue.push(payload); writeQueue(queue);
      setPending(queue.length);
      toast.error(`${e.response?.data?.detail || "Server unreachable"} — queued for retry`);
      setStepDone("queued"); setForm(blankForm());
    } finally { setSubmitting(false); }
  };

  return (
    <div className="min-h-screen bg-background pb-32" data-testid="dpr-mobile-page">
      {/* Sticky top bar */}
      <div className="sticky top-0 z-10 bg-background/95 backdrop-blur border-b border-border px-4 py-3 flex items-center gap-3">
        <Button variant="ghost" size="icon" className="rounded-sm" onClick={() => navigate("/app/dprs")} data-testid="dpr-mobile-back"><ChevronLeft className="h-5 w-5" /></Button>
        <div className="flex-1 min-w-0">
          <div className="text-[10px] uppercase tracking-wider text-primary font-bold">Site Capture</div>
          <div className="font-display font-black text-lg leading-tight truncate">Daily Site Report</div>
        </div>
        <div className="flex items-center gap-1.5">
          {online ? <span className="text-[10px] bg-success/10 text-success border border-success/30 rounded-sm px-2 py-1 font-bold">ONLINE</span>
            : <span className="text-[10px] bg-warning/10 text-warning border border-warning/30 rounded-sm px-2 py-1 font-bold flex items-center gap-1"><WifiOff className="h-3 w-3" /> OFFLINE</span>}
          {pending > 0 && <span className="text-[10px] bg-info/10 text-chart-3 border border-chart-3/30 rounded-sm px-2 py-1 font-bold" data-testid="dpr-mobile-pending">⟳ {pending}</span>}
        </div>
      </div>

      <div className="px-4 py-4 space-y-4 max-w-xl mx-auto">
        {stepDone && (
          <div className={`border rounded-sm p-3 flex items-start gap-3 ${stepDone === "ok" ? "bg-success/10 border-success/40" : "bg-warning/10 border-warning/40"}`} data-testid={`dpr-mobile-done-${stepDone}`}>
            {stepDone === "ok" ? <CheckCircle2 className="h-5 w-5 text-success shrink-0" /> : <AlertCircle className="h-5 w-5 text-warning shrink-0" />}
            <div className="text-xs flex-1">
              {stepDone === "ok" ? "DPR submitted successfully." : "Saved locally — will sync when you're back online."}
            </div>
            <Button size="sm" variant="ghost" className="h-7 rounded-sm" onClick={() => setStepDone(null)}><X className="h-3 w-3" /></Button>
          </div>
        )}

        {/* Section 1: Basics */}
        <Section title="Where & when">
          <MobileField label="Project code *" value={form.project_code} onChange={(v) => setForm({ ...form, project_code: v })} testid="dpr-m-project" placeholder="e.g. PRJ-2026-0042" />
          <MobileField label="Site name" value={form.site_name} onChange={(v) => setForm({ ...form, site_name: v })} testid="dpr-m-site" />
          <div className="grid grid-cols-2 gap-3">
            <MobileField label="Date" type="date" value={form.date} onChange={(v) => setForm({ ...form, date: v })} testid="dpr-m-date" />
            <MobileSelect label="Service" value={form.service_type} options={SERVICE_OPTIONS} onChange={(v) => setForm({ ...form, service_type: v })} testid="dpr-m-service" />
          </div>
        </Section>

        {/* Section 2: GPS */}
        <Section title="Site location (GPS)">
          <div className="flex items-center gap-3">
            <Button onClick={captureGps} className="h-12 rounded-sm flex-1" variant={form.gps ? "outline" : "default"} data-testid="dpr-m-gps-btn">
              <MapPin className="h-4 w-4 mr-2" />
              {gpsState === "locating" ? "Locating…" : form.gps ? "Refresh GPS" : "Capture GPS"}
            </Button>
            {form.gps && (
              <div className="text-[10px] text-success font-mono-data leading-tight">
                {form.gps.latitude.toFixed(5)}<br />{form.gps.longitude.toFixed(5)}<br />
                <span className="text-muted-foreground">±{form.gps.accuracy_m}m</span>
              </div>
            )}
          </div>
          {gpsState === "denied" && <p className="text-xs text-destructive mt-1.5">Location permission denied. Enable it in your browser settings to stamp the DPR.</p>}
        </Section>

        {/* Section 3: Manpower */}
        <Section title={`Manpower (${totalMen} present)`}>
          <div className="space-y-2">
            {form.manpower.map((m, i) => (
              <div key={`mp-${i}`} className="flex items-center gap-2" data-testid={`dpr-m-mp-row-${i}`}>
                <select value={m.role} onChange={(e) => setForm({ ...form, manpower: form.manpower.map((x, ix) => ix === i ? { ...x, role: e.target.value } : x) })} className="h-12 flex-1 rounded-sm border border-input bg-background px-3 text-sm" data-testid={`dpr-m-mp-role-${i}`}>
                  {SITE_ROLES.map((r) => <option key={r} value={r}>{r.replaceAll("_", " ")}</option>)}
                </select>
                <button type="button" className="h-12 w-12 rounded-sm border border-input bg-background font-bold text-lg" onClick={() => setForm({ ...form, manpower: form.manpower.map((x, ix) => ix === i ? { ...x, count: Math.max(0, Number(x.count) - 1) } : x) })} data-testid={`dpr-m-mp-minus-${i}`}>−</button>
                <Input type="number" inputMode="numeric" value={m.count} onChange={(e) => setForm({ ...form, manpower: form.manpower.map((x, ix) => ix === i ? { ...x, count: Number(e.target.value) || 0 } : x) })} className="h-12 w-16 rounded-sm text-center text-base font-bold tabular" data-testid={`dpr-m-mp-count-${i}`} />
                <button type="button" className="h-12 w-12 rounded-sm border border-input bg-background font-bold text-lg" onClick={() => setForm({ ...form, manpower: form.manpower.map((x, ix) => ix === i ? { ...x, count: Number(x.count) + 1 } : x) })} data-testid={`dpr-m-mp-plus-${i}`}>+</button>
              </div>
            ))}
          </div>
          <Button variant="outline" className="h-10 rounded-sm w-full mt-2" onClick={() => setForm({ ...form, manpower: [...form.manpower, { role: "helper", count: 0 }] })} data-testid="dpr-m-mp-add">+ Add role</Button>
        </Section>

        {/* Section 4: Photos */}
        <Section title={`Site photos (${form.photos.length}/6)`}>
          <input ref={cameraRef} type="file" accept="image/*" capture="environment" multiple onChange={(e) => addPhotos(e.target.files)} className="hidden" data-testid="dpr-m-photo-input" />
          <Button className="h-14 rounded-sm w-full" onClick={() => cameraRef.current?.click()} data-testid="dpr-m-photo-btn"><Camera className="h-5 w-5 mr-2" /> Capture photo</Button>
          {form.photos.length > 0 && (
            <div className="grid grid-cols-3 gap-2 mt-3">
              {form.photos.map((p, i) => (
                <div key={`ph-${i}`} className="relative aspect-square rounded-sm overflow-hidden border border-border" data-testid={`dpr-m-photo-${i}`}>
                  <img src={p.dataUrl} alt={p.name} className="w-full h-full object-cover" />
                  <button type="button" className="absolute top-1 right-1 bg-destructive text-destructive-foreground rounded-sm p-1" onClick={() => setForm({ ...form, photos: form.photos.filter((_, ix) => ix !== i) })}><X className="h-3 w-3" /></button>
                </div>
              ))}
            </div>
          )}
        </Section>

        {/* Section 5: Work narrative */}
        <Section title="Work & observations">
          <MobileArea label="Work completed" value={form.work_completed} onChange={(v) => setForm({ ...form, work_completed: v })} testid="dpr-m-work" placeholder="What got done today?" />
          <MobileArea label="Safety observations" value={form.safety_observations} onChange={(v) => setForm({ ...form, safety_observations: v })} testid="dpr-m-safety" placeholder="Near-misses, PPE compliance, hazards…" />
          <MobileArea label="Client instructions" value={form.client_instructions} onChange={(v) => setForm({ ...form, client_instructions: v })} testid="dpr-m-client" placeholder="Verbal/written instructions on site" />
          <MobileArea label="Delay reasons" value={form.delay_reasons} onChange={(v) => setForm({ ...form, delay_reasons: v })} testid="dpr-m-delay" placeholder="Weather, manpower short, client hold…" />
          <MobileArea label="Extra work" value={form.extra_work} onChange={(v) => setForm({ ...form, extra_work: v })} testid="dpr-m-extra" />
          <MobileArea label="Supervisor remarks" value={form.supervisor_remarks} onChange={(v) => setForm({ ...form, supervisor_remarks: v })} testid="dpr-m-remarks" />
        </Section>
      </div>

      {/* Sticky action bar */}
      <div className="fixed bottom-0 inset-x-0 bg-background/95 backdrop-blur border-t border-border px-4 py-3 flex gap-2 z-20">
        <Button variant="outline" className="h-12 rounded-sm flex-1" onClick={() => submit(false)} disabled={submitting} data-testid="dpr-m-save-draft">Save Draft</Button>
        <Button className="h-12 rounded-sm flex-1" onClick={() => submit(true)} disabled={submitting} data-testid="dpr-m-submit"><Send className="h-4 w-4 mr-2" /> Submit</Button>
        {pending > 0 && online && <Button variant="outline" className="h-12 rounded-sm" onClick={flushQueue} data-testid="dpr-m-sync"><RotateCcw className="h-4 w-4" /></Button>}
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="bg-card border border-border rounded-sm p-3">
      <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-2">{title}</div>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function MobileField({ label, value, onChange, type = "text", testid, placeholder }) {
  return (
    <div>
      <Label className="text-[11px] uppercase tracking-wider">{label}</Label>
      <Input type={type} value={value ?? ""} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} className="h-12 rounded-sm mt-1 text-base" data-testid={testid} />
    </div>
  );
}

function MobileArea({ label, value, onChange, testid, placeholder }) {
  return (
    <div>
      <Label className="text-[11px] uppercase tracking-wider">{label}</Label>
      <Textarea value={value ?? ""} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} className="rounded-sm mt-1 min-h-[64px] text-base" data-testid={testid} />
    </div>
  );
}

function MobileSelect({ label, value, options, onChange, testid }) {
  return (
    <div>
      <Label className="text-[11px] uppercase tracking-wider">{label}</Label>
      <select value={value || ""} onChange={(e) => onChange(e.target.value)} className="h-12 w-full rounded-sm border border-input bg-background px-3 text-base mt-1" data-testid={testid}>
        {options.map((o) => <option key={o} value={o}>{(o || "").replaceAll("_", " ")}</option>)}
      </select>
    </div>
  );
}
