import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";

/**
 * Reads `?q=` and `?hl=` set by the universal search and highlights the matching row.
 * Rows opt in with `data-row-id={row.id}`; the hit row gets `.search-hit` for a few seconds.
 * Pass `onQuery` to seed the page's local filter input with the search term once.
 */
export default function useSearchLanding(onQuery, deps = []) {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") || "";
  const hl = params.get("hl") || "";

  useEffect(() => {
    if (q && onQuery) onQuery(q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  useEffect(() => {
    if (!hl) return undefined;
    let tries = 0;
    const timer = setInterval(() => {
      const el = document.querySelector(`[data-row-id="${hl}"]`);
      tries += 1;
      if (el) {
        clearInterval(timer);
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.classList.add("search-hit");
        setTimeout(() => el.classList.remove("search-hit"), 6000);
        const next = new URLSearchParams(params);
        next.delete("hl");
        setParams(next, { replace: true });
      } else if (tries > 40) clearInterval(timer);
    }, 250);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hl, ...deps]);

  return { q, hl };
}
