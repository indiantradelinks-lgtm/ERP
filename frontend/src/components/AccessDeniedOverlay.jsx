import { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { ShieldX } from "lucide-react";
import { Button } from "@/components/ui/button";

/** Full-screen friendly notice when the user opens a project that isn't assigned to them. */
export default function AccessDeniedOverlay() {
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const show = () => setOpen(true);
    window.addEventListener("project-access-denied", show);
    return () => window.removeEventListener("project-access-denied", show);
  }, []);

  useEffect(() => { setOpen(false); }, [location.pathname]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[100] bg-background/85 backdrop-blur-sm flex items-center justify-center p-6" data-testid="access-denied-overlay">
      <div className="max-w-md w-full border border-border rounded-sm bg-card shadow-xl p-8 text-center">
        <div className="mx-auto h-14 w-14 rounded-full bg-red-50 border border-red-200 flex items-center justify-center mb-4">
          <ShieldX className="h-7 w-7 text-red-500" />
        </div>
        <h2 className="font-display font-bold text-lg mb-1">This project isn't assigned to you</h2>
        <p className="text-sm text-muted-foreground mb-6">
          The project you tried to open is handled by another team. If it was recently
          transferred, ask your Project Head to reassign it — access updates instantly.
        </p>
        <div className="flex justify-center gap-2">
          <Button variant="outline" onClick={() => { setOpen(false); nav("/app/ops/my-projects"); }} data-testid="access-denied-my-projects">My Projects</Button>
          <Button onClick={() => { setOpen(false); nav("/app"); }} data-testid="access-denied-home">Go to Dashboard</Button>
        </div>
      </div>
    </div>
  );
}
