import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";

export default function Logistics() {
  const r = useResource("vehicles");
  const columns = [
    { key: "reg_number", label: "Reg #" },
    { key: "type", label: "Type" },
    { key: "capacity", label: "Capacity" },
    { key: "driver", label: "Driver" },
    { key: "last_service", label: "Last Service" },
    { key: "fuel_avg", label: "Fuel (km/L)" },
    { key: "status", label: "Status", badge: (r) => ({ text: r.status, tone: r.status === "active" ? "success" : r.status === "maintenance" ? "warning" : "neutral" }) },
  ];
  const fields = [
    { key: "reg_number", label: "Registration No" },
    { key: "type", label: "Type", type: "select", options: ["truck", "pickup", "crane", "trailer", "bus", "car"] },
    { key: "capacity", label: "Capacity" },
    { key: "driver", label: "Driver Name", full: true },
    { key: "last_service", label: "Last Service Date", type: "date" },
    { key: "fuel_avg", label: "Fuel Avg (km/L)", type: "number" },
    { key: "status", label: "Status", type: "select", options: ["active", "maintenance", "idle"] },
  ];
  return <DataTableShell title="Logistics · Vehicles" description="Fleet, drivers, fuel and trip readiness." data={r.data} columns={columns} fields={fields} onCreate={r.create} onUpdate={r.update} onDelete={r.remove} testidPrefix="logistics" />;
}
