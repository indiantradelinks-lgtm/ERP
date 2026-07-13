import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";

export default function SafetyTrainings() {
  const r = useResource("safety-trainings");
  const columns = [
    { key: "title", label: "Training" },
    { key: "trainer", label: "Trainer" },
    { key: "date", label: "Date" },
    { key: "duration_hrs", label: "Hrs" },
    { key: "attendees_count", label: "Attendees" },
    { key: "project", label: "Project" },
  ];
  const fields = [
    { key: "title", label: "Title", full: true },
    { key: "trainer", label: "Trainer" },
    { key: "date", label: "Date", type: "date" },
    { key: "duration_hrs", label: "Duration (hrs)", type: "number" },
    { key: "attendees_count", label: "Attendee Count", type: "number" },
    { key: "project", label: "Project Code" },
    { key: "topics", label: "Topics Covered", type: "textarea", full: true },
  ];
  return <DataTableShell title="Safety Trainings" description="Mandatory and refresher training sessions for site staff." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="safety-trainings" exportResource="safety-trainings" canWrite={r.canWrite} canDelete={r.canDelete} attachmentsParentType="safety" />;
}
