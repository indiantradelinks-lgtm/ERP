import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";

/**
 * Generic server-paged list for endpoints returning {rows,total,pages} when `page>=1`.
 * Returns { rows, pagination, search, setSearch, reload } — `pagination` plugs into <TablePager/>.
 */
export default function usePagedList(url, filters = {}, { pageSize: initial = 50, errorLabel = "records" } = {}) {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(initial);
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [loading, setLoading] = useState(true);
  const seq = useRef(0);
  const filterKey = JSON.stringify(filters);

  useEffect(() => {
    const t = setTimeout(() => { setDebounced(search); setPage(1); }, 350);
    return () => clearTimeout(t);
  }, [search]);

  const firstKey = useRef(filterKey);
  useEffect(() => {
    if (firstKey.current !== filterKey) { firstKey.current = filterKey; setPage(1); }
  }, [filterKey]);

  const load = useCallback(async () => {
    const my = ++seq.current;
    setLoading(true);
    try {
      const qs = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      if (debounced.trim()) qs.set("search", debounced.trim());
      Object.entries(JSON.parse(filterKey)).forEach(([k, v]) => { if (v) qs.set(k, String(v)); });
      const { data } = await api.get(`${url}${url.includes("?") ? "&" : "?"}${qs.toString()}`);
      if (my !== seq.current) return;
      setRows(data.rows || []);
      setTotal(data.total || 0);
    } catch (e) {
      if (my === seq.current) toast.error(e.response?.data?.detail || `Failed to load ${errorLabel}`);
    } finally {
      if (my === seq.current) setLoading(false);
    }
  }, [url, page, pageSize, debounced, filterKey, errorLabel]);

  useEffect(() => { load(); }, [load]);

  const pagination = {
    page, pageSize, total, loading, pages: Math.max(1, Math.ceil(total / pageSize)),
    setPage, setPageSize: (n) => { setPageSize(n); setPage(1); },
  };
  return { rows, pagination, search, setSearch, reload: load, loading };
}
