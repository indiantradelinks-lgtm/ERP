export const DEFAULT_SORT = { by: "created_at", dir: "desc" };

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

/** Builds the `pagination.views` object consumed by <TableViewsMenu/>. */
export function buildViewsApi(view, current, setters, defaultPageSize = 50, defaultSort = DEFAULT_SORT) {
  if (!view?.active) return null;
  const state = { search: current.search, sort_by: current.sort.by, sort_dir: current.sort.dir, page_size: current.pageSize };
  const defaults = { search: "", sort_by: defaultSort.by, sort_dir: defaultSort.dir, page_size: defaultPageSize };
  const apply = (s) => {
    setters.setSearch(typeof s.search === "string" ? s.search : "");
    setters.setSort({ by: s.sort_by || defaultSort.by, dir: s.sort_dir === "asc" ? "asc" : "desc" });
    setters.setPageSize(Number(s.page_size) || defaultPageSize);
    setters.setPage(1);
  };
  return {
    presets: view.presets,
    shared: view.shared || [],
    canPublish: !!view.canPublish,
    publishShared: (name, department) => view.publishShared(name, state, department),
    unpublishShared: view.unpublishShared,
    isDefault: same(state, defaults),
    activePresetId: ([...view.presets, ...(view.shared || [])].find((p) => same({ ...defaults, ...p.state }, state)) || {}).id || null,
    savePreset: (name) => view.savePreset(name, state),
    deletePreset: view.deletePreset,
    applyPreset: (p) => apply(p.state || {}),
    resetView: () => { apply(defaults); view.reset(); },
  };
}
