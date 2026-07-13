import { useEffect, useMemo, useRef } from "react";
import { MapContainer, TileLayer, Marker, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";

// Bundle Leaflet's default marker icons via webpack so they work offline /
// when unpkg is blocked. react-leaflet doesn't auto-resolve these.
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

function ClickToPlace({ onPick }) {
  useMapEvents({
    click(e) { onPick(e.latlng); },
  });
  return null;
}

function Recenter({ lat, lng }) {
  const map = useMap();
  useEffect(() => {
    if (lat && lng && !Number.isNaN(lat) && !Number.isNaN(lng)) {
      map.setView([lat, lng], Math.max(map.getZoom(), 11));
    }
  }, [lat, lng, map]);
  return null;
}

/**
 * Tiny editable Leaflet map. Click anywhere on the map or drag the pin to set
 * lat/lng. Calls `onChange({lat, lng})` whenever the position updates.
 */
export default function LeafletPinEditor({ lat, lng, onChange, height = 220 }) {
  const numericLat = useMemo(() => (lat === "" || lat == null ? null : parseFloat(lat)), [lat]);
  const numericLng = useMemo(() => (lng === "" || lng == null ? null : parseFloat(lng)), [lng]);
  const hasPin = numericLat !== null && numericLng !== null && !Number.isNaN(numericLat) && !Number.isNaN(numericLng);
  const center = hasPin ? [numericLat, numericLng] : [20.5937, 78.9629]; // centre of India fallback
  const zoom = hasPin ? 11 : 4;
  const markerRef = useRef(null);

  return (
    <div className="rounded-sm border border-border overflow-hidden" data-testid="leaflet-pin-editor">
      <MapContainer center={center} zoom={zoom} style={{ height, width: "100%" }} scrollWheelZoom={false}>
        <TileLayer
          attribution='&copy; OpenStreetMap'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <ClickToPlace onPick={(latlng) => onChange({ lat: latlng.lat.toFixed(6), lng: latlng.lng.toFixed(6) })} />
        {hasPin && <Recenter lat={numericLat} lng={numericLng} />}
        {hasPin && (
          <Marker
            position={[numericLat, numericLng]}
            draggable
            ref={markerRef}
            eventHandlers={{
              dragend(e) {
                const ll = e.target.getLatLng();
                onChange({ lat: ll.lat.toFixed(6), lng: ll.lng.toFixed(6) });
              },
            }}
          />
        )}
      </MapContainer>
      <div className="flex items-center justify-between bg-muted/30 px-2 py-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
        <span>Click map or drag pin · OpenStreetMap</span>
        <button
          type="button"
          className="text-primary font-bold hover:underline"
          data-testid="leaflet-use-my-location"
          onClick={() => {
            if (!navigator.geolocation) { return; }
            navigator.geolocation.getCurrentPosition(
              (p) => onChange({ lat: p.coords.latitude.toFixed(6), lng: p.coords.longitude.toFixed(6) }),
              () => {},
              { enableHighAccuracy: true, timeout: 8000 },
            );
          }}
        >Use my location</button>
      </div>
    </div>
  );
}
