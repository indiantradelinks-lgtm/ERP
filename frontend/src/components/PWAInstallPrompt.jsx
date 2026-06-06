import { useEffect, useState } from "react";
import { Download, X, WifiOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

/**
 * Two affordances:
 *  1. Catches the `beforeinstallprompt` event and renders an "Install app"
 *     toast / sticky bottom-right card.
 *  2. Listens for `online`/`offline` and renders a small pill at the top.
 *
 * Dismissed-install state is persisted in localStorage so the prompt does not
 * harass returning visitors.
 */
const DISMISS_KEY = "wsc_install_dismissed_v1";

export default function PWAInstallPrompt() {
  const [deferred, setDeferred] = useState(null);
  const [show, setShow] = useState(false);
  const [offline, setOffline] = useState(typeof navigator !== "undefined" && !navigator.onLine);

  useEffect(() => {
    const onBeforeInstall = (e) => {
      e.preventDefault();
      if (localStorage.getItem(DISMISS_KEY) === "1") return;
      setDeferred(e);
      setShow(true);
    };
    const onInstalled = () => {
      setShow(false);
      setDeferred(null);
      toast.success("WorkSite Command installed");
    };
    const onOnline = () => setOffline(false);
    const onOffline = () => setOffline(true);
    window.addEventListener("beforeinstallprompt", onBeforeInstall);
    window.addEventListener("appinstalled", onInstalled);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstall);
      window.removeEventListener("appinstalled", onInstalled);
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  const install = async () => {
    if (!deferred) return;
    deferred.prompt();
    const { outcome } = await deferred.userChoice;
    if (outcome === "accepted") {
      toast.success("Installing…");
    }
    setDeferred(null);
    setShow(false);
  };

  const dismiss = () => {
    localStorage.setItem(DISMISS_KEY, "1");
    setShow(false);
  };

  return (
    <>
      {offline && (
        <div
          className="fixed top-2 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 bg-warning/95 text-warning-foreground px-3 py-1.5 rounded-sm text-xs font-bold uppercase tracking-wider shadow-sm"
          data-testid="pwa-offline-pill"
        >
          <WifiOff className="h-3.5 w-3.5" /> Offline — limited functionality
        </div>
      )}
      {show && (
        <div
          className="fixed bottom-4 right-4 z-50 max-w-xs bg-card border border-border rounded-sm shadow-lg p-4 stagger"
          data-testid="pwa-install-card"
        >
          <div className="flex items-start gap-3">
            <div className="h-9 w-9 rounded-sm bg-primary/10 text-primary grid place-items-center shrink-0">
              <Download className="h-4 w-4" />
            </div>
            <div className="flex-1">
              <div className="font-display font-bold text-sm">Install WorkSite Command</div>
              <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                Add to your home screen for one-tap access and offline shell.
              </p>
              <div className="flex gap-2 mt-3">
                <Button size="sm" className="h-8 rounded-sm" onClick={install} data-testid="pwa-install-btn">
                  Install
                </Button>
                <Button size="sm" variant="ghost" className="h-8 rounded-sm" onClick={dismiss} data-testid="pwa-dismiss-btn">
                  Not now
                </Button>
              </div>
            </div>
            <button
              className="text-muted-foreground hover:text-foreground"
              onClick={dismiss}
              aria-label="Dismiss install prompt"
              data-testid="pwa-close-btn"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
