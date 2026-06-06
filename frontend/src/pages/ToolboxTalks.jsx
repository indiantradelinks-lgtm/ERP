import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";

export default function ToolboxTalks() {
  const r = useResource("toolbox-talks");
  const columns = [
    { key: "date", label: "Date" },
    { key: "topic", label: "Topic" },
    { key: "site", label: "Site" },
    { key: "led_by", label: "Conducted By" },
    { key: "attendees_count", label: "Attendees" },
  ];
  const fields = [
    { key: "date", label: "Date", type: "date" },
    { key: "topic", label: "Topic", full: true },
    { key: "site", label: "Site / Location" },
    { key: "led_by", label: "Conducted By" },
    { key: "attendees_count", label: "Attendees", type: "number" },
    { key: "key_messages", label: "Key Messages", type: "textarea", full: true },
  ];
  return <DataTableShell title="Toolbox Talks" description="Daily site briefings logged with topic, attendance and key messages." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="toolbox" exportResource="toolbox-talks" canWrite={r.canWrite} canDelete={r.canDelete} attachmentsParentType="safety" />;
}
