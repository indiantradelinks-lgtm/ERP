import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

// Map URL slug -> backend permission key (collection name).
const SLUG_TO_PERM = {
  clients: "clients",
  vendors: "vendors",
  employees: "employees",
  attendance: "attendance",
  projects: "projects",
  inventory: "inventory",
  "purchase-orders": "purchase_orders",
  quotations: "quotations",
  "journal-entries": "journal_entries",
  "safety-reports": "safety_reports",
  assets: "assets",
  payroll: "payroll",
  vehicles: "vehicles",
  documents: "documents",
  approvals: "approvals",
};

export default function useResource(resource) {
  const { can } = useAuth() || { can: () => true };
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  const permKey = SLUG_TO_PERM[resource] || resource;
  const canRead = can(permKey, "read");
  const canWrite = can(permKey, "write");
  const canDelete = can(permKey, "delete");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/${resource}`);
      setData(Array.isArray(data) ? data : []);
    } catch (e) {
      if (e.response?.status === 403) {
        // silent — UI handles via canRead
      } else {
        toast.error(`Failed to load ${resource}`);
      }
    } finally {
      setLoading(false);
    }
  }, [resource]);

  useEffect(() => { load(); }, [load]);

  const create = async (payload) => {
    try {
      const { data: row } = await api.post(`/${resource}`, payload);
      setData((d) => [row, ...d]);
      toast.success("Created");
      return row;
    } catch (e) {
      toast.error(e.response?.data?.detail || "Create failed");
    }
  };

  const update = async (id, payload) => {
    try {
      const { data: row } = await api.put(`/${resource}/${id}`, payload);
      setData((d) => d.map((r) => (r.id === id ? row : r)));
      toast.success("Updated");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Update failed");
    }
  };

  const remove = async (id) => {
    if (!window.confirm("Delete this item?")) return;
    try {
      await api.delete(`/${resource}/${id}`);
      setData((d) => d.filter((r) => r.id !== id));
      toast.success("Deleted");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Delete failed");
    }
  };

  return { data, loading, reload: load, create, update, remove, canRead, canWrite, canDelete, exportResource: resource };
}
