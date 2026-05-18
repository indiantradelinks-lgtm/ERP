import { api } from "@/lib/api";
import { toast } from "sonner";

/** Trigger a browser download for /api/export/{resource}.{fmt}. */
export async function downloadExport(resource, fmt) {
  try {
    const { data, headers } = await api.get(`/export/${resource}.${fmt}`, { responseType: "blob" });
    const cd = headers["content-disposition"] || "";
    const match = /filename="?([^";]+)"?/.exec(cd);
    const filename = match?.[1] || `${resource}.${fmt}`;
    const blob = new Blob([data], { type: data.type || (fmt === "xlsx" ? "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" : "application/pdf") });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
    toast.success(`Downloaded ${filename}`);
  } catch {
    toast.error("Export failed");
  }
}
