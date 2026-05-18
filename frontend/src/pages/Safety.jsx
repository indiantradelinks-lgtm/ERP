import { useState, useEffect } from "react";
import DataTableShell, { StatusBadge } from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import FileUploader from "@/components/FileUploader";
import { Camera } from "lucide-react";
import { api } from "@/lib/api";

export default function Safety() {
  const r = useResource("safety-reports");
  const [active, setActive] = useState(null);
  const [open, setOpen] = useState(false);
  const [photos, setPhotos] = useState([]);

  const openPhotos = async (row) => {
    setActive(row);
    setOpen(true);
    try {
      const { data } = await api.get(`/files?folder=safety&parent_type=safety_reports&parent_id=${row.id}`);
      setPhotos(data || []);
    } catch (e) { setPhotos([]); }
  };

  const columns = [
    { key: "report_id", label: "Report" },
    { key: "date", label: "Date" },
    { key: "project", label: "Project" },
    { key: "type", label: "Type", render: (r) => (r.type || "").replaceAll("_", " ") },
    { key: "severity", label: "Severity", badge: (r) => ({ text: r.severity, tone: r.severity === "high" ? "danger" : r.severity === "medium" ? "warning" : "success" }) },
    { key: "reporter", label: "Reporter" },
    { key: "status", label: "Status", badge: (r) => ({ text: r.status, tone: r.status === "closed" ? "success" : r.status === "open" ? "warning" : "info" }) },
    {
      key: "_photos",
      label: "Photos",
      render: (row) => (
        <Button size="sm" variant="outline" className="h-7 rounded-sm" onClick={() => openPhotos(row)} data-testid={`safety-photos-${row.id}`}>
          <Camera className="h-3.5 w-3.5 mr-1" /> Photos
        </Button>
      ),
    },
  ];
  const fields = [
    { key: "report_id", label: "Report ID" },
    { key: "date", label: "Date", type: "date" },
    { key: "project", label: "Project", full: true },
    { key: "type", label: "Type", type: "select", options: ["observation", "near_miss", "incident", "ptw", "toolbox_talk"] },
    { key: "severity", label: "Severity", type: "select", options: ["low", "medium", "high"] },
    { key: "reporter", label: "Reporter" },
    { key: "description", label: "Description", full: true, type: "textarea" },
    { key: "status", label: "Status", type: "select", options: ["open", "under_review", "closed"] },
  ];

  return (
    <>
      <DataTableShell
        title="Safety Management"
        description="Observations, near-miss, incidents and PTWs. Tap Photos to attach site evidence."
        data={r.data}
        columns={columns}
        fields={fields}
        onCreate={r.create}
        onUpdate={r.update}
        onDelete={r.remove}
        testidPrefix="safety"
        exportResource={r.exportResource}
        canWrite={r.canWrite}
        canDelete={r.canDelete}
      />
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl rounded-sm" data-testid="safety-photos-dialog">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2">
              <Camera className="h-5 w-5 text-primary" />
              {active?.report_id} · {active?.type?.replaceAll("_", " ")}
            </DialogTitle>
          </DialogHeader>
          {active && (
            <div className="space-y-3">
              <div className="text-xs text-muted-foreground">{active.description || "—"}</div>
              <FileUploader
                folder="safety"
                parent_type="safety_reports"
                parent_id={active.id}
                files={photos}
                onUploaded={(f) => setPhotos((s) => [f, ...s])}
                onDeleted={(id) => setPhotos((s) => s.filter((x) => x.id !== id))}
                accept="image/*"
                capture="environment"
                testidPrefix="safety-uploader"
                compact
              />
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} className="rounded-sm">Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
