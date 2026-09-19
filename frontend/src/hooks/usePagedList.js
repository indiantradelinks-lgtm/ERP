import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import useTableView from "@/hooks/useTableView";
import { buildViewsApi } from "@/hooks/tableViewState";

/**
 * Generic server-paged list for endpoints returning {rows,total,pages} when `page>=1`.
 * opts: { pageSize=50, errorLabel, viewKey (enables saved views), searchKeys (csv), defaultSort {by,dir} }
 * Returns { rows, pagination, search, setSearch, reload, loading, total } — `pagination` plugs into <TablePager/>.
 */
export default function usePagedList(url, filters = {}, opts = {}) {
  const { pageSize: initial = 50, errorLabel = "records", viewKey = null, searchKeys = "", defaultSort = { by: "created_at", dir: "desc" }, enabled = true, transform = null } = opts;
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(initial);
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [sort, setSort] = useState(defaultSort);
  const [loading, setLoading] = useState(true);
  const seq = useRef(0);
  const filterKey = JSON.stringify(filters);
  const view = useTableView(viewKey, !!viewKey);
  const [viewApplied, setViewApplied] = useState(!viewKey);

  useEffect(() => {
    if (!view.ready || viewApplied) return;
    const s = view.initial;
    if (s) {
      if (typeof s.search === "string") { setSearch(s.search); setDebounced(s.search); }
      if (s.sort_by) setSort({ by: s.sort_by, dir: s.sort_dir === "asc" ? "asc" : "desc" });
      if (s.page_size) setPageSize(Number(s.page_size));
    }
    setViewApplied(true);
  }, [view.ready, view.initial, viewApplied]);

  useEffect(() => {
    const t = setTimeout(() => { if (search !== debounced) { setDebounced(search); setPage(1); } }, 350);
    return () => clearTimeout(t);
  }, [search, debounced]);

  const firstKey = useRef(filterKey);
  useEffect(() => {
    if (firstKey.current !== filterKey) { firstKey.current = filterKey; setPage(1); }
  }, [filterKey]);

  const load = useCallback(async () => {
    if (!viewApplied || !enabled) return;
    const my = ++seq.current;
    setLoading(true);
    try {
      const qs = new URLSearchParams({ page: String(page), page_size: String(pageSize), sort_by: sort.by, sort_dir: sort.dir });
      if (debounced.trim()) qs.set("search", debounced.trim());
      if (searchKeys) qs.set("search_keys", searchKeys);
      Object.entries(JSON.parse(filterKey)).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") qs.set(k, String(v)); });
      const { data } = await api.get(`${url}${url.includes("?") ? "&" : "?"}${qs.toString()}`);
      if (my !== seq.current) return;
      let list = Array.isArray(data) ? data : (data.rows || []);
      if (transform) list = await transform(list);
      if (my !== seq.current) return;
      setRows(list);
      setTotal(Array.isArray(data) ? data.length : (data.total || 0));
    } catch (e) {
      if (my === seq.current) toast.error(e.response?.data?.detail || `Failed to load ${errorLabel}`);
    } finally {
      if (my === seq.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewApplied, enabled, url, page, pageSize, debounced, sort.by, sort.dir, filterKey, errorLabel, searchKeys]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (viewApplied) view.persist({ search: debounced, sort_by: sort.by, sort_dir: sort.dir, page_size: pageSize });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewApplied, debounced, sort.by, sort.dir, pageSize]);

  const pagination = useMemo(() => {
    const setters = { setSearch: (v) => { setSearch(v); setDebounced(v); }, setSort, setPageSize, setPage };
    return {
      page, pageSize, total, loading, search, sort, pages: Math.max(1, Math.ceil(total / pageSize)),
      setPage,
      setPageSize: (n) => { setPageSize(n); setPage(1); },
      setSearch,
      setSort: (by) => { setSort((s) => ({ by, dir: s.by === by && s.dir === "desc" ? "asc" : "desc" })); setPage(1); },
      views: buildViewsApi(view, { search: debounced, sort, pageSize }, setters, initial, defaultSort),
    };
  }, [page, pageSize, total, loading, search, debounced, sort, view, initial, defaultSort]);

  return { rows, pagination, search, setSearch, reload: load, loading, total };
}
