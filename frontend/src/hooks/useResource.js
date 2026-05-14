import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";

export default function useResource(resource) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/${resource}`);
      setData(Array.isArray(data) ? data : []);
    } catch (e) {
      toast.error(`Failed to load ${resource}`);
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
      toast.error("Create failed");
    }
  };

  const update = async (id, payload) => {
    try {
      const { data: row } = await api.put(`/${resource}/${id}`, payload);
      setData((d) => d.map((r) => (r.id === id ? row : r)));
      toast.success("Updated");
    } catch (e) {
      toast.error("Update failed");
    }
  };

  const remove = async (id) => {
    if (!window.confirm("Delete this item?")) return;
    try {
      await api.delete(`/${resource}/${id}`);
      setData((d) => d.filter((r) => r.id !== id));
      toast.success("Deleted");
    } catch (e) {
      toast.error("Delete failed");
    }
  };

  return { data, loading, reload: load, create, update, remove };
}
