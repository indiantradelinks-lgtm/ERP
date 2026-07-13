import { Component } from "react";
import { Button } from "@/components/ui/button";
import { AlertTriangle, RotateCw } from "lucide-react";

/**
 * Generic error boundary. Catches render errors in subtree and shows a
 * recoverable fallback panel instead of unmounting the whole app.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error("[ErrorBoundary]", error, info?.componentStack);
  }

  reset = () => this.setState({ error: null });

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div
        className="bg-card border border-destructive/30 rounded-sm p-6 max-w-2xl mx-auto my-10"
        data-testid="error-boundary-fallback"
      >
        <div className="flex items-start gap-3">
          <div className="h-10 w-10 grid place-items-center rounded-sm bg-destructive/15 text-destructive shrink-0">
            <AlertTriangle className="h-5 w-5" />
          </div>
          <div className="flex-1">
            <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-destructive">
              Something went wrong
            </div>
            <h2 className="font-display font-bold text-lg mt-0.5">
              This view crashed while rendering
            </h2>
            <p className="text-sm text-muted-foreground mt-1.5">
              {error?.message || "An unexpected error occurred."}
            </p>
            <div className="flex gap-2 mt-4">
              <Button
                onClick={this.reset}
                className="rounded-sm h-9"
                data-testid="error-boundary-retry"
              >
                <RotateCw className="h-4 w-4 mr-1.5" /> Try again
              </Button>
              <Button
                variant="outline"
                onClick={() => window.location.reload()}
                className="rounded-sm h-9"
                data-testid="error-boundary-reload"
              >
                Reload page
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  }
}
