import { useEffect, useState } from "react";
import { Bell, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import { api } from "@/lib/api";
import { Link } from "react-router-dom";

export default function NotificationBell() {
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);

  const load = async () => {
    try {
      const { data } = await api.get("/notifications/mine?limit=20");
      setItems(data.items || []);
      setUnread(data.unread || 0);
    } catch { /* ignore — non-critical */ }
  };

  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t); }, []);

  const markRead = async (id) => {
    setItems((it) => it.map((n) => (n.id === id ? { ...n, read: true } : n)));
    setUnread((u) => Math.max(0, u - 1));
    try { await api.post(`/notifications/${id}/read`); } catch { /* swallow */ }
  };

  const markAll = async () => {
    setItems((it) => it.map((n) => ({ ...n, read: true })));
    setUnread(0);
    try { await api.post("/notifications/read-all"); } catch { /* swallow */ }
  };

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className="relative" data-testid="notification-bell">
          <Bell className="h-5 w-5" />
          {unread > 0 && (
            <span className="absolute -top-0.5 -right-0.5 bg-rose-600 text-white text-[10px] rounded-full h-4 min-w-4 px-1 flex items-center justify-center font-bold">
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-96 p-0" data-testid="notification-panel">
        <div className="p-3 border-b flex items-center justify-between">
          <div className="font-semibold text-sm">Notifications</div>
          {unread > 0 && (
            <Button variant="ghost" size="sm" onClick={markAll} className="text-xs h-7" data-testid="notif-mark-all-read">
              <Check className="h-3 w-3 mr-1" /> Mark all read
            </Button>
          )}
        </div>
        <div className="max-h-96 overflow-y-auto">
          {items.length === 0 && (
            <div className="p-8 text-center text-xs text-muted-foreground">No notifications yet.</div>
          )}
          {items.map((n) => (
            <div
              key={n.id}
              className={`p-3 border-b text-xs hover:bg-slate-50 ${!n.read ? "bg-blue-50" : ""}`}
              data-testid={`notif-${n.id}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="font-semibold truncate">{n.title}</div>
                  {n.body && <div className="text-muted-foreground mt-0.5 line-clamp-2">{n.body}</div>}
                  <div className="text-[10px] text-muted-foreground mt-1 flex items-center gap-2">
                    <Badge variant="outline" className="text-[9px] py-0 px-1 h-4">{(n.type || "").replaceAll("_", " ")}</Badge>
                    <span>{(n.at || "").slice(0, 16).replace("T", " ")}</span>
                  </div>
                </div>
                {!n.read && (
                  <Button size="sm" variant="ghost" className="h-5 px-1" onClick={() => markRead(n.id)} data-testid={`notif-read-${n.id}`}>
                    <Check className="h-3 w-3" />
                  </Button>
                )}
              </div>
              {n.link && (
                <Link to={n.link} className="text-blue-600 hover:underline text-[10px] mt-1 inline-block" onClick={() => markRead(n.id)}>
                  Open →
                </Link>
              )}
            </div>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
