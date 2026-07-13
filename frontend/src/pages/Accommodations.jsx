import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";

export default function Accommodations() {
  const r = useResource("accommodations");
  const columns = [
    { key: "camp", label: "Camp / Building" },
    { key: "room_no", label: "Room" },
    { key: "capacity", label: "Capacity" },
    { key: "occupants_count", label: "Occupied" },
    { key: "occupant_names", label: "Occupants" },
    { key: "project", label: "Project" },
  ];
  const fields = [
    { key: "camp", label: "Camp / Building" },
    { key: "room_no", label: "Room Number" },
    { key: "capacity", label: "Bed Capacity", type: "number" },
    { key: "occupants_count", label: "Current Occupants", type: "number" },
    { key: "occupant_names", label: "Occupant Names", type: "textarea", full: true },
    { key: "project", label: "Linked Project" },
    { key: "rent_per_month", label: "Rent / Month (INR)", type: "number" },
  ];
  return <DataTableShell title="Accommodations" description="Room / camp allocation, capacity and occupancy." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="accommodations" exportResource="accommodations" canWrite={r.canWrite} canDelete={r.canDelete} />;
}
