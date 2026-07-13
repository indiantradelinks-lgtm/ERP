import { useEffect, useMemo, useState } from "react";
import { MapContainer, TileLayer, Marker, Popup } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";
import { MapPin, Building2, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/DataTableShell";
import { api } from "@/lib/api";
import { toast } from "sonner";

// Bundle the default Leaflet marker icons (avoids relying on unpkg CDN).
const DEFAULT_ICON = L.icon({
  iconUrl: markerIcon,
  iconRetinaUrl: markerIcon2x,
  shadowUrl: markerShadow,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});
L.Marker.prototype.options.icon = DEFAULT_ICON;

const STATUS_TONE = { active: "success", on_hold: "warning", inactive: "neutral" };

export default function ClientMap() {
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [hovered, setHovered] = useState(null);

  useEffect(() => {
    setLoading(true);
    api.get("/sites/map")
      .then((r) => setSites(r.data || []))
      .catch((e) => toast.error(e.response?.data?.detail || "Failed to load map"))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    if (!query.trim()) return sites;
    const q = query.toLowerCase();
    return sites.filter((s) =>
      [s.site_code, s.name, s.client_name, s.city, s.state].some((v) => String(v || "").toLowerCase().includes(q)),
    );
  }, [sites, query]);

  const center = useMemo(() => {
    if (filtered.length === 0) return [20.5937, 78.9629];
    const lat = filtered.reduce((a, s) => a + s.geo_lat, 0) / filtered.length;
    const lng = filtered.reduce((a, s) => a + s.geo_lng, 0) / filtered.length;
    return [lat, lng];
  }, [filtered]);

  return (
    <div className="space-y-6" data-testid="client-map">
      <div>
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-primary mb-1.5 flex items-center gap-2">
          <MapPin className="h-3 w-3" /> Sales · Customer Geography
        </div>
        <h1 className="font-display font-black text-3xl tracking-tight">Client Map</h1>
        <p className="text-sm text-muted-foreground mt-1">All geo-tagged customer sites on a single interactive map. Click a marker for details.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-card border border-border rounded-sm overflow-hidden" data-testid="client-map-canvas">
          {loading && <div className="h-[520px] grid place-items-center text-sm text-muted-foreground">Loading map…</div>}
          {!loading && (
            <MapContainer center={center} zoom={filtered.length ? 5 : 4} style={{ height: 520, width: "100%" }} scrollWheelZoom>
              <TileLayer
                attribution='&copy; OpenStreetMap'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              {filtered.map((s) => (
                <Marker
                  key={s.id}
                  position={[s.geo_lat, s.geo_lng]}
                  eventHandlers={{ mouseover: () => setHovered(s.id) }}
                >
                  <Popup>
                    <div className="text-xs">
                      <div className="font-bold font-mono mb-0.5">{s.site_code}</div>
                      <div className="font-semibold">{s.client_name}</div>
                      <div className="text-muted-foreground">{s.name}</div>
                      <div>{s.city}, {s.state}</div>
                      <div className="mt-1 text-[10px]">Status: {s.status}</div>
                    </div>
                  </Popup>
                </Marker>
              ))}
            </MapContainer>
          )}
        </div>

        <div className="bg-card border border-border rounded-sm flex flex-col" data-testid="client-map-sidebar">
          <div className="p-3 border-b border-border space-y-2">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                className="h-9 rounded-sm pl-9"
                placeholder="Search site / client / city…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                data-testid="client-map-search"
              />
            </div>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
              {filtered.length} of {sites.length} sites geo-tagged
            </div>
          </div>
          <ul className="overflow-y-auto divide-y divide-border flex-1 max-h-[460px]">
            {filtered.length === 0 && !loading && (
              <li className="text-center text-xs text-muted-foreground py-10 px-3" data-testid="client-map-empty">
                No geo-tagged sites yet. Open a site, drop a pin on the mini-map, save.
              </li>
            )}
            {filtered.map((s) => (
              <li
                key={s.id}
                className={`p-3 hover:bg-muted/30 cursor-default ${hovered === s.id ? "bg-muted/40" : ""}`}
                data-testid={`client-map-row-${s.id}`}
                onMouseEnter={() => setHovered(s.id)}
              >
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <span className="font-mono-data text-[11px] bg-chart-3/10 text-chart-3 px-1.5 py-0.5 rounded-sm font-bold">{s.site_code}</span>
                  <StatusBadge text={s.status || "active"} tone={STATUS_TONE[s.status] || "neutral"} />
                </div>
                <div className="text-sm font-semibold truncate flex items-center gap-1.5">
                  <Building2 className="h-3 w-3 text-muted-foreground shrink-0" /> {s.client_name}
                </div>
                <div className="text-[11px] text-muted-foreground truncate">{s.name} · {s.city}, {s.state}</div>
                <div className="text-[10px] font-mono-data text-muted-foreground/80 mt-0.5">{s.geo_lat.toFixed(4)}, {s.geo_lng.toFixed(4)}</div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
