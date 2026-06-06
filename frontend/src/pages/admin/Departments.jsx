import DataTableShell from "@/components/DataTableShell";
import useResource from "@/hooks/useResource";

export default function Departments() {
  const r = useResource("departments");
  const columns = [
    { key: "code", label: "Code" },
    { key: "name", label: "Department" },
    { key: "head", label: "Department Head" },
    { key: "parent", label: "Parent" },
    { key: "description", label: "Description" },
  ];
  const fields = [
    { key: "code", label: "Code" },
    { key: "name", label: "Name" },
    { key: "head", label: "Department Head" },
    { key: "parent", label: "Parent Department" },
    { key: "description", label: "Description", type: "textarea", full: true },
  ];
  return (
    <DataTableShell
      title="Departments"
      description="Master list of organisational departments — used across HRMS, projects and approval routing."
      data={r.data}
      columns={columns}
      fields={fields}
      onCreate={r.create}
      onUpdate={r.update}
      onDelete={r.remove}
      testidPrefix="departments"
      canWrite={r.canWrite}
      canDelete={r.canDelete}
    />
  );
}
