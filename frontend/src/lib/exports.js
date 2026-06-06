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


/** Download/open an authenticated PDF from any backend path.
 *  Usage: downloadPdf(`/procurement/prs/${id}/pdf`, `PR-${num}.pdf`)
 *  If `inline` is true (default), opens the PDF in a new tab; otherwise forces download.
 */
export async function downloadPdf(path, filename, { inline = true } = {}) {
  try {
    const { data, headers } = await api.get(path, { responseType: "blob" });
    const cd = headers["content-disposition"] || "";
    const match = /filename="?([^";]+)"?/.exec(cd);
    const fname = filename || match?.[1] || "document.pdf";
    const blob = new Blob([data], { type: data.type || "application/pdf" });
    const url = window.URL.createObjectURL(blob);
    if (inline) {
      window.open(url, "_blank");
    } else {
      const a = document.createElement("a");
      a.href = url;
      a.download = fname;
      document.body.appendChild(a);
      a.click();
      a.remove();
    }
    setTimeout(() => window.URL.revokeObjectURL(url), 60000);
  } catch (e) {
    toast.error(e?.response?.data?.detail || "PDF generation failed");
  }
}
