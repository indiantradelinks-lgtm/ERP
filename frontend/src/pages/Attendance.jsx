import { useState } from "react";
import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";
import { Button } from "@/components/ui/button";
import { MapPin } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { toneFor } from "@/lib/statusTone";

const ATTENDANCE_STATUS_TONE = { present: "success", absent: "danger" };

/** Capture the current geolocation via the browser API (PWA-friendly).
 *  Resolves with {lat, lng, accuracy} or rejects with a human-readable error.
 */
function getGeolocation() {
  return new Promise((resolve, reject) => {
    if (!("geolocation" in navigator)) {
      reject(new Error("Geolocation is not supported on this device."));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({
        lat: pos.coords.latitude,
        lng: pos.coords.longitude,
        accuracy: pos.coords.accuracy,
      }),
      (err) => reject(new Error(err.message || "Unable to read location")),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
    );
  });
}

export default function Attendance() {
  const r = useResource("attendance");
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);

  const markPresent = async () => {
    setBusy(true);
    try {
      const geo = await getGeolocation().catch((e) => { toast.warning(`No geo: ${e.message}`); return null; });
      const now = new Date();
      await api.post("/attendance", {
        employee_name: user?.name || "Me",
        employee_id: user?.id,
        date: now.toISOString().slice(0, 10),
        check_in: now.toTimeString().slice(0, 5),
        status: "present",
        ...(geo ? { geo_lat: geo.lat, geo_lng: geo.lng, geo_accuracy: Math.round(geo.accuracy) } : {}),
      });
      toast.success(geo ? `Marked present (±${Math.round(geo.accuracy)} m)` : "Marked present");
      r.reload();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed");
    } finally {
      setBusy(false);
    }
  };

  const columns = [
    { key: "date", label: "Date" },
    { key: "employee_name", label: "Employee" },
    { key: "check_in", label: "In" },
    { key: "check_out", label: "Out" },
    { key: "hours", label: "Hours" },
    {
      key: "_geo",
      label: "Geo",
      render: (row) => (row.geo_lat ? (
        <a
          href={`https://maps.google.com/?q=${row.geo_lat},${row.geo_lng}`}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs text-primary hover:underline font-mono-data"
          data-testid={`attendance-geo-${row.id}`}
        >
          <MapPin className="h-3 w-3" /> {row.geo_lat.toFixed(4)}, {row.geo_lng.toFixed(4)}
        </a>
      ) : <span className="text-[10px] text-muted-foreground">—</span>),
    },
    { key: "status", label: "Status", badge: (row) => ({ text: row.status, tone: toneFor(ATTENDANCE_STATUS_TONE, row.status, "warning") }) },
  ];
  const fields = [
    { key: "employee_name", label: "Employee Name", full: true },
    { key: "date", label: "Date", type: "date" },
    { key: "check_in", label: "Check In (HH:MM)" },
    { key: "check_out", label: "Check Out (HH:MM)" },
    { key: "hours", label: "Hours", type: "number" },
    { key: "status", label: "Status", type: "select", options: ["present", "absent", "leave", "half_day"] },
  ];

  const extraActions = r.canWrite ? (
    <Button onClick={markPresent} disabled={busy} className="rounded-sm" data-testid="attendance-mark-present">
      <MapPin className="h-4 w-4 mr-1.5" /> {busy ? "Marking…" : "Mark Present"}
    </Button>
  ) : null;

  return (
    <DataTableShell
      title="Attendance"
      description="Daily check-in/out records by employee — geo-tagged when the device permits."
      data={r.data}
      columns={columns}
      fields={fields}
      onCreate={r.create}
      onUpdate={r.update}
      onDelete={r.remove}
      testidPrefix="attendance"
      exportResource={r.exportResource}
      canWrite={r.canWrite}
      canDelete={r.canDelete}
      extraActions={extraActions}
    />
  );
}
