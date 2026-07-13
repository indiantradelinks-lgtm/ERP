import { useEffect, useRef, useState } from "react";
import { Camera, X, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";

/**
 * Camera-based barcode scanner using the browser's BarcodeDetector API
 * (Chrome/Edge/Samsung Internet/Android Chrome). On unsupported browsers
 * (Firefox/Safari < 17) we render a clear unsupported state with a hint to
 * use the keyboard input instead.
 *
 * Props:
 *   open       — controlled visibility
 *   onOpenChange(nextOpen)
 *   onDetected(code) — called once with the decoded string; we auto-close
 *   formats    — optional list of barcode formats; defaults to a sensible set
 */
const DEFAULT_FORMATS = [
  "qr_code", "code_128", "code_39", "code_93", "ean_13", "ean_8",
  "itf", "pdf417", "upc_a", "upc_e", "data_matrix",
];

export default function BarcodeScanner({ open, onOpenChange, onDetected, formats = DEFAULT_FORMATS }) {
  const videoRef = useRef(null);
  const rafRef = useRef(null);
  const streamRef = useRef(null);
  const onDetectedRef = useRef(onDetected);
  const [error, setError] = useState(null);
  const [scanning, setScanning] = useState(false);
  const supported = typeof window !== "undefined" && "BarcodeDetector" in window;

  // Keep the callback ref up to date without re-mounting the effect (which
  // would restart the camera and prompt for permission every parent render).
  useEffect(() => {
    onDetectedRef.current = onDetected;
  }, [onDetected]);

  useEffect(() => {
    if (!open || !supported) return;
    let cancelled = false;
    let detector;

    const start = async () => {
      try {
        // eslint-disable-next-line no-undef
        detector = new BarcodeDetector({ formats });
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" } },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
        setScanning(true);
        const tick = async () => {
          if (cancelled || !videoRef.current) return;
          try {
            const codes = await detector.detect(videoRef.current);
            if (codes && codes.length > 0) {
              const code = codes[0].rawValue;
              onDetectedRef.current?.(code);
              stop();
              return;
            }
          } catch {
            // detector.detect can throw intermittently — ignore and continue
          }
          rafRef.current = requestAnimationFrame(tick);
        };
        rafRef.current = requestAnimationFrame(tick);
      } catch (e) {
        setError(e?.message || "Unable to access the camera. Please grant permission and retry.");
        setScanning(false);
      }
    };

    const stop = () => {
      cancelled = true;
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
      setScanning(false);
    };

    start();
    return stop;
  }, [open, supported, formats]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md rounded-sm" data-testid="barcode-scanner">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">
            <Camera className="h-4 w-4 text-primary" /> Scan Barcode / QR
          </DialogTitle>
          <DialogDescription className="sr-only">
            Point the camera at any 1D/2D code. The scanner closes automatically on the first match.
          </DialogDescription>
        </DialogHeader>

        {!supported ? (
          <div className="flex flex-col items-center gap-3 py-8 text-center" data-testid="barcode-unsupported">
            <div className="h-12 w-12 rounded-sm bg-warning/15 text-warning grid place-items-center">
              <AlertTriangle className="h-6 w-6" />
            </div>
            <div className="font-display font-bold">Camera scanning not supported</div>
            <p className="text-xs text-muted-foreground max-w-xs">
              Your browser doesn't support the <code className="font-mono-data">BarcodeDetector</code> API.
              Please use Chrome on Android / Edge / Samsung Internet, or fall back to manual SKU entry.
            </p>
          </div>
        ) : (
          <div className="relative bg-black rounded-sm overflow-hidden aspect-video" data-testid="barcode-video-frame">
            <video ref={videoRef} className="w-full h-full object-cover" playsInline muted aria-label="Camera viewfinder for barcode scanning">
              <track kind="captions" />
            </video>
            {/* Crosshair overlay */}
            <div className="pointer-events-none absolute inset-0 grid place-items-center">
              <div className="w-3/4 aspect-video border-2 border-primary/80 rounded-sm shadow-[0_0_0_9999px_rgba(0,0,0,0.35)]">
                <div className="w-full h-0.5 bg-primary mt-[50%] animate-pulse" />
              </div>
            </div>
            {!scanning && (
              <div className="absolute inset-0 grid place-items-center text-white text-sm">Starting camera…</div>
            )}
            {error && (
              <div className="absolute inset-x-0 bottom-0 bg-destructive/95 text-destructive-foreground text-xs p-2 text-center">{error}</div>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={() => onOpenChange(false)} data-testid="barcode-close">
            <X className="h-4 w-4 mr-1.5" /> Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
