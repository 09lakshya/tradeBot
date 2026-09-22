"use client";

import React, { useState, useMemo } from "react";
import { useNotificationStore, NotificationCategory, NotificationSeverity } from "@/stores/useNotificationStore";
import {
  Bell,
  X,
  CheckCheck,
  Archive,
  Search,
  AlertTriangle,
  Info,
  CheckCircle,
  AlertCircle,
  ShieldAlert,
  Trash2,
  Filter,
} from "lucide-react";

const CATEGORIES: ("ALL" | NotificationCategory)[] = [
  "ALL",
  "Orders",
  "Risk",
  "Strategies",
  "Portfolio",
  "Operations",
  "System",
  "Market",
  "Alerts",
];

export function NotificationCenter() {
  const {
    notifications,
    isCenterOpen,
    setCenterOpen,
    markAsRead,
    markAllAsRead,
    archiveNotification,
    clearAll,
  } = useNotificationStore();

  const [selectedCategory, setSelectedCategory] = useState<"ALL" | NotificationCategory>("ALL");
  const [selectedSeverity, setSelectedSeverity] = useState<"ALL" | NotificationSeverity>("ALL");
  const [showOnlyUnread, setShowOnlyUnread] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const unreadCount = useMemo(
    () => notifications.filter((n) => !n.read && !n.archived).length,
    [notifications]
  );

  const filteredNotifications = useMemo(() => {
    return notifications.filter((n) => {
      if (!showArchived && n.archived) return false;
      if (showArchived && !n.archived) return false;
      if (showOnlyUnread && n.read) return false;
      if (selectedCategory !== "ALL" && n.category !== selectedCategory) return false;
      if (selectedSeverity !== "ALL" && n.severity !== selectedSeverity) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return n.title.toLowerCase().includes(q) || n.message.toLowerCase().includes(q);
      }
      return true;
    });
  }, [notifications, showArchived, showOnlyUnread, selectedCategory, selectedSeverity, searchQuery]);

  const getSeverityIcon = (sev: NotificationSeverity) => {
    switch (sev) {
      case "success":
        return <CheckCircle className="w-4 h-4 text-emerald-400" />;
      case "warning":
        return <AlertTriangle className="w-4 h-4 text-amber-400" />;
      case "error":
        return <AlertCircle className="w-4 h-4 text-rose-400" />;
      case "critical":
        return <ShieldAlert className="w-4 h-4 text-purple-400 animate-pulse" />;
      case "info":
      default:
        return <Info className="w-4 h-4 text-sky-400" />;
    }
  };

  if (!isCenterOpen) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex justify-end">
      <div className="w-full max-w-md bg-slate-900 border-l border-slate-800 h-full flex flex-col shadow-2xl animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="p-4 border-b border-slate-800 bg-slate-950 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Bell className="w-5 h-5 text-emerald-400" />
            <h3 className="text-sm font-bold text-slate-100 uppercase tracking-wider">
              Notification Center
            </h3>
            {unreadCount > 0 && (
              <span className="px-2 py-0.5 text-xs font-bold font-mono rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                {unreadCount} Unread
              </span>
            )}
          </div>

          <button
            onClick={() => setCenterOpen(false)}
            className="text-slate-400 hover:text-slate-100 p-1 rounded-lg hover:bg-slate-800"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Toolbar & Filters */}
        <div className="p-3 border-b border-slate-800 bg-slate-900/80 space-y-2 text-xs font-mono">
          {/* Search Box */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="Search notifications..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-md pl-8 pr-3 py-1.5 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500"
            />
          </div>

          {/* Category Tabs */}
          <div className="flex items-center gap-1 overflow-x-auto pb-1 scrollbar-none">
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`px-2 py-0.5 rounded text-[11px] font-medium whitespace-nowrap transition ${
                  selectedCategory === cat
                    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                    : "bg-slate-800 text-slate-400 hover:text-slate-200"
                }`}
              >
                {cat}
              </button>
            ))}
          </div>

          {/* Severity & Actions Row */}
          <div className="flex items-center justify-between pt-1 text-[11px]">
            <div className="flex items-center gap-1">
              <button
                onClick={() => setShowOnlyUnread(!showOnlyUnread)}
                className={`px-2 py-0.5 rounded border transition ${
                  showOnlyUnread ? "bg-cyan-500/20 border-cyan-500/40 text-cyan-300" : "bg-slate-950 border-slate-800 text-slate-400"
                }`}
              >
                Unread Only
              </button>

              <button
                onClick={() => setShowArchived(!showArchived)}
                className={`px-2 py-0.5 rounded border transition ${
                  showArchived ? "bg-purple-500/20 border-purple-500/40 text-purple-300" : "bg-slate-950 border-slate-800 text-slate-400"
                }`}
              >
                Archived
              </button>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={markAllAsRead}
                className="text-slate-400 hover:text-emerald-400 flex items-center gap-1"
                title="Mark all as read"
              >
                <CheckCheck className="w-3.5 h-3.5" />
                Read All
              </button>

              <button
                onClick={clearAll}
                className="text-slate-400 hover:text-rose-400 p-1"
                title="Clear all notifications"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>

        {/* Notifications List */}
        <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
          {filteredNotifications.length === 0 ? (
            <div className="text-center text-slate-500 py-12 font-mono text-xs">
              {/* Distinguish "nothing has happened yet" from "your filter hides it". */}
              {notifications.length === 0
                ? "No notifications yet."
                : "No notifications matching current view filters."}
            </div>
          ) : (
            filteredNotifications.map((notif) => (
              <div
                key={notif.id}
                onClick={() => markAsRead(notif.id)}
                className={`p-3 rounded-lg border transition-all cursor-pointer relative group ${
                  notif.read
                    ? "bg-slate-950/40 border-slate-800/80 text-slate-400"
                    : "bg-slate-900 border-slate-700/80 text-slate-100 shadow-md border-l-4 border-l-emerald-400"
                }`}
              >
                <div className="flex items-start justify-between gap-2 mb-1">
                  <div className="flex items-center gap-2">
                    {getSeverityIcon(notif.severity)}
                    <span className="font-semibold text-xs text-slate-200">{notif.title}</span>
                  </div>
                  <span className="text-[10px] font-mono text-slate-500">{notif.timestamp}</span>
                </div>

                <p className="text-xs text-slate-300 font-mono leading-relaxed pl-6">{notif.message}</p>

                <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-800/60 pl-6 text-[10px] font-mono">
                  <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 uppercase">
                    {notif.category}
                  </span>

                  {!notif.archived && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        archiveNotification(notif.id);
                      }}
                      className="text-slate-500 hover:text-purple-400 opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1"
                    >
                      <Archive className="w-3 h-3" />
                      Archive
                    </button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
