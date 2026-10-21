import { useEffect, useRef, useState } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Eye, PenLine, Info } from "lucide-react";
import { api } from "@/lib/api";

const PREVIEW_CSS = `
.tnc-prev { font-size: 12px; color: #334155; line-height: 1.6; }
.tnc-prev .tnc-heading { font-weight: 700; color: #0f172a; margin: 12px 0 5px; }
.tnc-prev .tnc-heading:first-child { margin-top: 0; }
.tnc-prev .tnc-item { padding-left: 26px; text-indent: -26px; margin: 0 0 7px; text-align: justify; }
.tnc-prev .tnc-sub { padding-left: 52px; text-indent: -26px; margin-bottom: 5px; }
.tnc-prev .tnc-bullet { padding-left: 40px; text-indent: -14px; margin-bottom: 5px; }
.tnc-prev .tnc-num { display: inline-block; width: 26px; text-indent: 0; font-weight: 700; color: #0f172a; }
.tnc-prev .tnc-bullet .tnc-num { width: 14px; }
.tnc-prev .tnc-para { margin: 0 0 7px; text-align: justify; }
.tnc-prev .tnc-gap { height: 6px; }
.tnc-prev .note { color: #64748b; font-style: italic; }
`;

const GUIDE = [
  "Plain lines are numbered automatically — 1., 2., 3. …",
  "Already numbered a clause yourself (1., 2.1, 3.1.2)? Auto numbering steps aside — your numbers print as typed",
  "HEADINGS IN CAPS, **Bold Heading** or a short line ending with a colon print as a heading, unnumbered",
  "Start a line with - or • for a bullet point",
  "Leave a blank line to separate blocks",
];

export default function TermsEditor({ value, onChange, rows = 10, testid = "terms-body", label = "Terms & Conditions (printed on the PO)" }) {
  const [mode, setMode] = useState("write");
  const [html, setHtml] = useState("");
  const [meta, setMeta] = useState({ manual_numbering: false, lines: 0 });
  const [guide, setGuide] = useState(false);
  const timer = useRef(null);

  useEffect(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try {
        const { data } = await api.post("/service-workflow/terms/preview", { body: value || "" });
        setHtml(data.html);
        setMeta({ manual_numbering: data.manual_numbering, lines: data.lines });
      } catch { setHtml("<div class='note'>Preview unavailable</div>"); }
    }, 250);
    return () => clearTimeout(timer.current);
  }, [mode, value]);

  return (
    <div data-testid={`${testid}-editor`}>
      <style>{PREVIEW_CSS}</style>
      <div className="flex items-center justify-between gap-2 mb-1">
        <Label className="text-xs">{label}</Label>
        <div className="flex items-center gap-1">
          <Button type="button" variant="ghost" size="sm" className="h-6 px-2 text-[11px]" onClick={() => setGuide((g) => !g)} data-testid={`${testid}-guide-toggle`}>
            <Info className="h-3 w-3 mr-1" /> Formatting
          </Button>
          <Button type="button" variant={mode === "write" ? "secondary" : "ghost"} size="sm" className="h-6 px-2 text-[11px]" onClick={() => setMode("write")} data-testid={`${testid}-mode-write`}>
            <PenLine className="h-3 w-3 mr-1" /> Write
          </Button>
          <Button type="button" variant={mode === "preview" ? "secondary" : "ghost"} size="sm" className="h-6 px-2 text-[11px]" onClick={() => setMode("preview")} data-testid={`${testid}-mode-preview`}>
            <Eye className="h-3 w-3 mr-1" /> Preview
          </Button>
        </div>
      </div>
      {guide && (
        <ul className="text-[11px] text-muted-foreground bg-muted/40 border border-border rounded-sm p-2 mb-1 space-y-0.5 list-disc pl-5" data-testid={`${testid}-guide`}>
          {GUIDE.map((g) => <li key={g}>{g}</li>)}
        </ul>
      )}
      {mode === "write" ? (
        <Textarea rows={rows} value={value || ""} onChange={(e) => onChange(e.target.value)}
          placeholder={"One clause per line for auto numbering — or paste a formatted set with your own headings, numbers and bullets."}
          className="font-mono text-[12px]" data-testid={testid} />
      ) : (
        <div className="border border-border rounded-sm bg-card p-3 max-h-[320px] overflow-y-auto" data-testid={`${testid}-preview`}>
          <div className="tnc-prev" dangerouslySetInnerHTML={{ __html: html || "<div class='note'>Nothing to preview yet.</div>" }} />
        </div>
      )}
      <p className="text-[10px] text-muted-foreground mt-1" data-testid={`${testid}-mode-hint`}>
        {meta.manual_numbering
          ? "Manual numbering detected — your clause numbers print exactly as typed, nothing is renumbered."
          : "Auto numbering is on — each plain clause line prints as 1., 2., 3. … on the PO PDF."}
      </p>
    </div>
  );
}
