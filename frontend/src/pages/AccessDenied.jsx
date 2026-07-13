/**
 * Access Denied page · shown by RouteGuard when the user lacks permission.
 */
import { useNavigate, useLocation } from "react-router-dom";
import { ShieldOff, ArrowLeft, Home } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useAuth } from "@/contexts/AuthContext";

export default function AccessDenied({ reason }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();
  return (
    <Card className="max-w-xl mx-auto mt-12" data-testid="page-access-denied">
      <CardContent className="p-8 text-center space-y-4">
        <div className="inline-flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
          <ShieldOff className="h-8 w-8 text-destructive" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold">Access Denied</h1>
          <p className="text-sm text-muted-foreground mt-2">
            {reason || "You don't have permission to view this page."}
          </p>
        </div>
        <div className="text-xs text-muted-foreground bg-muted/40 p-3 rounded-sm font-mono">
          <div>Route: <span className="text-foreground">{location.pathname}</span></div>
          <div>User: <span className="text-foreground">{user?.email}</span></div>
          <div>Role: <span className="text-foreground">{user?.role}</span></div>
        </div>
        <div className="flex justify-center gap-2 pt-2">
          <Button variant="outline" onClick={() => navigate(-1)} data-testid="btn-back">
            <ArrowLeft className="h-4 w-4 mr-1.5" /> Back
          </Button>
          <Button onClick={() => navigate("/app")} data-testid="btn-home">
            <Home className="h-4 w-4 mr-1.5" /> Dashboard
          </Button>
        </div>
        <p className="text-[10px] text-muted-foreground pt-3 border-t">
          If you believe this is an error, contact your administrator to update your role permissions.
        </p>
      </CardContent>
    </Card>
  );
}
