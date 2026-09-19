import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";

/**
 * Per-user saved table views (server-side): auto-remembered last state + named presets.
 * `initial` is the remembered state (or null) once `ready` flips true.
 */
export default function useTableView(key, enabled = true) {
  const active = !!key && enabled;
  const [ready, setReady] = useState(!active);
  const [initial, setInitial] = useState(null);
  const [presets, setPresets] = useState([]);
  const [shared, setShared] = useState([]);
  const [canPublish, setCanPublish] = useState(false);
  const timer = useRef(null);

  useEffect(() => {
    if (!active) return;
    let alive = true;
    api.get(`/table-views/${key}`)
      .then(({ data }) => {
        if (!alive) return;
        setInitial(data?.last || null); setPresets(data?.presets || []);
        setShared(data?.shared || []); setCanPublish(!!data?.can_publish);
      })
      .catch(() => {})
      .finally(() => { if (alive) setReady(true); });
    return () => { alive = false; };
  }, [key, active]);

  const persist = useCallback((state) => {
    if (!active) return;
    clearTimeout(timer.current);
    timer.current = setTimeout(() => api.put(`/table-views/${key}/last`, { state }).catch(() => {}), 800);
  }, [key, active]);
  useEffect(() => () => clearTimeout(timer.current), []);

  const savePreset = useCallback(async (name, state) => {
    try {
      const { data } = await api.post(`/table-views/${key}/presets`, { name, state });
      setPresets((p) => [...p.filter((x) => x.id !== data.id), data].sort((a, b) => a.name.localeCompare(b.name)));
      toast.success(`View "${name}" saved`);
    } catch (e) { toast.error(e.response?.data?.detail || "Could not save view"); }
  }, [key]);

  const deletePreset = useCallback(async (id) => {
    try {
      await api.delete(`/table-views/${key}/presets/${id}`);
      setPresets((p) => p.filter((x) => x.id !== id));
    } catch (e) { toast.error(e.response?.data?.detail || "Could not delete view"); }
  }, [key]);

  const publishShared = useCallback(async (name, state, department) => {
    try {
      const { data } = await api.post(`/table-views/${key}/shared`, { name, state, department: department || undefined });
      setShared((p) => [...p.filter((x) => x.id !== data.id), data].sort((a, b) => a.name.localeCompare(b.name)));
      toast.success(`Team view "${name}" published`);
    } catch (e) { toast.error(e.response?.data?.detail || "Could not publish view"); }
  }, [key]);

  const unpublishShared = useCallback(async (id) => {
    try {
      await api.delete(`/table-views/${key}/shared/${id}`);
      setShared((p) => p.filter((x) => x.id !== id));
    } catch (e) { toast.error(e.response?.data?.detail || "Could not remove team view"); }
  }, [key]);

  const reset = useCallback(() => { clearTimeout(timer.current); api.delete(`/table-views/${key}/last`).catch(() => {}); }, [key]);

  return { ready, initial, presets, shared, canPublish, persist, savePreset, deletePreset, publishShared, unpublishShared, reset, active };
}
