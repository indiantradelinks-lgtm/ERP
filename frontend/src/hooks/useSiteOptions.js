import { useEffect, useState } from "react";
import { api } from "@/lib/api";

/**
 * Returns a list of site dropdown options of the form
 *   [{ value: site_id, label: "CL-002-01 · Tata Steel HQ — Mumbai Hub" }, ...]
 * Uses the explicit site `name` when present; falls back to client + city.
 */
export default function useSiteOptions() {
  const [options, setOptions] = useState([]);
  useEffect(() => {
    api.get("/sites")
      .then((r) => {
        const opts = (r.data || []).map((s) => {
          const display = s.name || s.site_name || `${s.client_name || ""}${s.city ? " — " + s.city : ""}`;
          return {
            value: s.id,
            label: `${s.site_code} · ${display}`,
          };
        });
        setOptions(opts);
      })
      .catch(() => setOptions([]));
  }, []);
  return options;
}
