import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { api, apiErrorMessage } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import useTableView from "@/hooks/useTableView";
import { buildViewsApi, DEFAULT_SORT } from "@/hooks/tableViewState";

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

export const DEFAULT_PAGE_SIZE = 50;

/**
 * Server-paged resource hook. `data` holds ONLY the current page; `pagination`
 * drives DataTableShell's search / sort / pager / saved-views controls.
 * opts: { enabled=true, pageSize=50, params={} (extra query, e.g. f_status), viewKey=resource }
 */
export default function useResource(resource, opts = {}) {
  const { enabled = true, pageSize: initialPageSize = DEFAULT_PAGE_SIZE, params: extraParams, viewKey = resource } = opts;
  const { can } = useAuth() || { can: () => true };
  const [data, setData] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(enabled);
  const [loadError, setLoadError] = useState(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(initialPageSize);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState(DEFAULT_SORT);
  const searchKeysRef = useRef("");
  const reqSeq = useRef(0);
  const view = useTableView(viewKey, enabled);
  const [viewApplied, setViewApplied] = useState(false);

  const permKey = SLUG_TO_PERM[resource] || resource;
  const canRead = can(permKey, "read");
  const canWrite = can(permKey, "write");
  const canDelete = can(permKey, "delete");
  const extraKey = JSON.stringify(extraParams || {});

  // Apply the remembered view once before the first fetch
  useEffect(() => {
    if (!view.ready || viewApplied) return;
    const s = view.initial;
    if (s) {
      if (typeof s.search === "string") setSearch(s.search);
      if (s.sort_by) setSort({ by: s.sort_by, dir: s.sort_dir === "asc" ? "asc" : "desc" });
      if (s.page_size) setPageSize(Number(s.page_size));
    }
    setViewApplied(true);
  }, [view.ready, view.initial, viewApplied]);

  const load = useCallback(async (override = {}) => {
    if (!enabled || !viewApplied) return;
    const seq = ++reqSeq.current;
    setLoading(true);
    const p = override.page ?? page;
    const s = override.search ?? search;
    try {
      const qs = new URLSearchParams({ page: String(p), page_size: String(pageSize), sort_by: sort.by, sort_dir: sort.dir });
      if (s.trim()) qs.set("search", s.trim());
      if (searchKeysRef.current) qs.set("search_keys", searchKeysRef.current);
      Object.entries(JSON.parse(extraKey)).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") qs.set(k, String(v)); });
      const { data: res } = await api.get(`/${resource}?${qs.toString()}`);
      if (seq !== reqSeq.current) return;
      setData(Array.isArray(res) ? res : (res?.rows || []));
      setTotal(Array.isArray(res) ? res.length : (res?.total || 0));
      setLoadError(null);
    } catch (e) {
      if (seq !== reqSeq.current) return;
      if (e.response?.status === 403) {
        setLoadError(`Permission needed: your role cannot view '${resource}' on screen. Ask your admin to grant '${permKey} read' in the Role Register.`);
        toast.error(`No permission to view ${resource} — records exist but are hidden for your role. Ask admin for '${permKey} read'.`);
      } else {
        setLoadError(`Failed to load ${resource}${e.response?.status ? ` (HTTP ${e.response.status})` : ""}`);
        toast.error(`Failed to load ${resource}`);
      }
    } finally {
      if (seq === reqSeq.current) setLoading(false);
    }
  }, [enabled, viewApplied, resource, permKey, page, pageSize, sort.by, sort.dir, search, extraKey]);

  useEffect(() => { load(); }, [load]);

  // Remember the user's view (debounced, server-side) whenever it changes
  useEffect(() => {
    if (viewApplied) view.persist({ search, sort_by: sort.by, sort_dir: sort.dir, page_size: pageSize });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewApplied, search, sort.by, sort.dir, pageSize]);

  // Filters / page-size changed from outside → restart from page 1
  const firstExtra = useRef(extraKey);
  useEffect(() => {
    if (firstExtra.current !== extraKey) { firstExtra.current = extraKey; setPage(1); }
  }, [extraKey]);

  // Debounced search → always jump back to page 1
  const searchTimer = useRef(null);
  const setSearchDebounced = useCallback((value) => {
    setSearch(value);
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => setPage(1), 350);
  }, []);
  useEffect(() => () => clearTimeout(searchTimer.current), []);

  const create = useCallback(async (payload) => {
    try {
      const { data: row } = await api.post(`/${resource}`, payload);
      setData((d) => [row, ...d].slice(0, pageSize));
      setTotal((t) => t + 1);
      toast.success("Created");
      return row;
    } catch (e) {
      toast.error(apiErrorMessage(e, "Create failed"));
    }
  }, [resource, pageSize]);

  const update = useCallback(async (id, payload) => {
    try {
      const { data: row } = await api.put(`/${resource}/${id}`, payload);
      setData((d) => d.map((r) => (r.id === id ? row : r)));
      toast.success("Updated");
    } catch (e) {
      toast.error(apiErrorMessage(e, "Update failed"));
    }
  }, [resource]);

  const remove = useCallback(async (id) => {
    if (!window.confirm("Delete this item?")) return;
    try {
      await api.delete(`/${resource}/${id}`);
      setData((d) => d.filter((r) => r.id !== id));
      setTotal((t) => Math.max(0, t - 1));
      toast.success("Deleted");
    } catch (e) {
      toast.error(apiErrorMessage(e, "Delete failed"));
    }
  }, [resource]);

  const pagination = useMemo(() => {
    const setters = { setSearch, setSort, setPageSize, setPage };
    return {
      page, pageSize, total, loading, search, sort,
      pages: Math.max(1, Math.ceil(total / pageSize)),
      setPage,
      setPageSize: (n) => { setPageSize(n); setPage(1); },
      setSearch: setSearchDebounced,
      setSort: (by) => { setSort((s) => ({ by, dir: s.by === by && s.dir === "desc" ? "asc" : "desc" })); setPage(1); },
      setSearchKeys: (csv) => { searchKeysRef.current = csv; },
      views: buildViewsApi(view, { search, sort, pageSize }, setters, initialPageSize),
    };
  }, [page, pageSize, total, loading, search, sort, setSearchDebounced, view, initialPageSize]);

  return { data, total, loading, loadError, reload: load, create, update, remove, canRead, canWrite, canDelete, exportResource: resource, pagination };
}
