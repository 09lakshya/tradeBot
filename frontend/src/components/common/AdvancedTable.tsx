"use client";

import React, { useState, useMemo, useRef, useEffect } from "react";
import {
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Search,
  Download,
  Filter,
  Pin,
  Check,
  ChevronLeft,
  ChevronRight,
  Sparkles,
} from "lucide-react";

export interface ColumnDef<T> {
  key: string;
  header: string;
  accessor: (row: T) => any;
  cell?: (value: any, row: T) => React.ReactNode;
  sortable?: boolean;
  filterable?: boolean;
  pinned?: "left" | "right" | null;
  width?: number;
  minWidth?: number;
}

export interface SavedFilter {
  id: string;
  name: string;
  filterFn: (row: any) => boolean;
}

interface AdvancedTableProps<T> {
  data: T[];
  columns: ColumnDef<T>[];
  keyExtractor: (row: T) => string;
  title?: string;
  savedFilters?: SavedFilter[];
  onRowClick?: (row: T) => void;
  pageSize?: number;
  emptyMessage?: string;
}

type SortOrder = "asc" | "desc" | null;

interface SortState {
  key: string;
  order: SortOrder;
}

export function AdvancedTable<T>({
  data,
  columns: initialColumns,
  keyExtractor,
  title,
  savedFilters = [],
  onRowClick,
  pageSize = 15,
  emptyMessage = "No matching records found.",
}: AdvancedTableProps<T>) {
  const [searchQuery, setSearchQuery] = useState("");
  const [sorts, setSorts] = useState<SortState[]>([]);
  const [columns, setColumns] = useState<ColumnDef<T>[]>(initialColumns);
  const [activeFilterId, setActiveFilterId] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedIndex, setSelectedIndex] = useState<number>(-1);

  const containerRef = useRef<HTMLDivElement | null>(null);

  // Column Resizing state
  const [resizingColKey, setResizingColKey] = useState<string | null>(null);
  const [startX, setStartX] = useState<number>(0);
  const [startWidth, setStartWidth] = useState<number>(0);

  const handleResizeStart = (e: React.MouseEvent, colKey: string, currentWidth: number = 150) => {
    e.preventDefault();
    setResizingColKey(colKey);
    setStartX(e.clientX);
    setStartWidth(currentWidth);
  };

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!resizingColKey) return;
      const diff = e.clientX - startX;
      setColumns((prev) =>
        prev.map((c) => (c.key === resizingColKey ? { ...c, width: Math.max(c.minWidth || 60, startWidth + diff) } : c))
      );
    };

    const handleMouseUp = () => {
      setResizingColKey(null);
    };

    if (resizingColKey) {
      window.addEventListener("mousemove", handleMouseMove);
      window.addEventListener("mouseup", handleMouseUp);
    }
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [resizingColKey, startX, startWidth]);

  // Filter & Search Logic
  const filteredData = useMemo(() => {
    return data.filter((row) => {
      // Global Search
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const matchesQuery = columns.some((col) => {
          const val = col.accessor(row);
          return val !== undefined && val !== null && String(val).toLowerCase().includes(query);
        });
        if (!matchesQuery) return false;
      }

      // Saved Filter Predicate
      if (activeFilterId) {
        const filterObj = savedFilters.find((f) => f.id === activeFilterId);
        if (filterObj && !filterObj.filterFn(row)) {
          return false;
        }
      }

      return true;
    });
  }, [data, searchQuery, activeFilterId, columns, savedFilters]);

  // Multi-column Sort Logic
  const sortedData = useMemo(() => {
    if (sorts.length === 0) return filteredData;

    return [...filteredData].sort((a, b) => {
      for (const sort of sorts) {
        const col = columns.find((c) => c.key === sort.key);
        if (!col || !sort.order) continue;

        const valA = col.accessor(a);
        const valB = col.accessor(b);

        if (valA < valB) return sort.order === "asc" ? -1 : 1;
        if (valA > valB) return sort.order === "asc" ? 1 : -1;
      }
      return 0;
    });
  }, [filteredData, sorts, columns]);

  // Pagination Windowing
  const totalPages = Math.ceil(sortedData.length / pageSize) || 1;
  const paginatedData = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return sortedData.slice(start, start + pageSize);
  }, [sortedData, currentPage, pageSize]);

  // Multi-sort handler
  const handleSort = (colKey: string, isShiftPressed: boolean) => {
    setSorts((prev) => {
      const existingIndex = prev.findIndex((s) => s.key === colKey);
      if (existingIndex > -1) {
        const existing = prev[existingIndex];
        let nextOrder: SortOrder = "asc";
        if (existing.order === "asc") nextOrder = "desc";
        else if (existing.order === "desc") nextOrder = null;

        if (isShiftPressed) {
          if (!nextOrder) return prev.filter((s) => s.key !== colKey);
          const updated = [...prev];
          updated[existingIndex] = { key: colKey, order: nextOrder };
          return updated;
        } else {
          return nextOrder ? [{ key: colKey, order: nextOrder }] : [];
        }
      } else {
        return isShiftPressed ? [...prev, { key: colKey, order: "asc" }] : [{ key: colKey, order: "asc" }];
      }
    });
  };

  // Column Pinning Handler
  const togglePin = (colKey: string) => {
    setColumns((prev) =>
      prev.map((c) => {
        if (c.key === colKey) {
          const nextPin = c.pinned === "left" ? "right" : c.pinned === "right" ? null : "left";
          return { ...c, pinned: nextPin };
        }
        return c;
      })
    );
  };

  // CSV Export
  const exportCSV = () => {
    const headers = columns.map((c) => `"${c.header}"`).join(",");
    const rows = sortedData.map((row) =>
      columns
        .map((c) => {
          const val = c.accessor(row);
          return `"${String(val ?? "").replace(/"/g, '""')}"`;
        })
        .join(",")
    );
    const csvContent = "data:text/csv;charset=utf-8," + [headers, ...rows].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `${title ? title.toLowerCase().replace(/\s+/g, "_") : "export"}_data.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Keyboard Navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => Math.min(prev + 1, paginatedData.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => Math.max(prev - 1, 0));
    } else if (e.key === "Enter" && selectedIndex >= 0 && selectedIndex < paginatedData.length) {
      e.preventDefault();
      if (onRowClick) onRowClick(paginatedData[selectedIndex]);
    }
  };

  // Organized Pinned Columns Order
  const orderedColumns = useMemo(() => {
    const leftPinned = columns.filter((c) => c.pinned === "left");
    const unpinned = columns.filter((c) => !c.pinned);
    const rightPinned = columns.filter((c) => c.pinned === "right");
    return [...leftPinned, ...unpinned, ...rightPinned];
  }, [columns]);

  return (
    <div
      ref={containerRef}
      onKeyDown={handleKeyDown}
      tabIndex={0}
      role="grid"
      aria-label={title || "Advanced Data Table"}
      className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden shadow-xl focus:outline-none focus:ring-1 focus:ring-emerald-500/50"
    >
      {/* Table Header Controls */}
      <div className="p-3 bg-slate-950/70 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          {title && <h4 className="text-sm font-semibold text-slate-200 tracking-wide">{title}</h4>}

          {/* Saved Filter Badges */}
          {savedFilters.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-[11px] font-mono text-slate-500 flex items-center gap-1">
                <Filter className="w-3 h-3" /> Filters:
              </span>
              <button
                onClick={() => setActiveFilterId(null)}
                className={`px-2 py-0.5 text-[11px] rounded transition ${
 activeFilterId === null
                    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                    : "bg-slate-800 text-slate-400 hover:text-slate-200"
                }`}
              >
                All
              </button>
              {savedFilters.map((f) => (
                <button
                  key={f.id}
                  onClick={() => setActiveFilterId(f.id)}
                  className={`px-2 py-0.5 text-[11px] rounded transition ${
 activeFilterId === f.id
                      ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-medium"
                      : "bg-slate-800 text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {f.name}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Search Box */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setCurrentPage(1);
              }}
              placeholder="Search table..."
              className="bg-slate-900 border border-slate-700/80 rounded-md pl-8 pr-3 py-1 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500 w-44 md:w-56"
            />
          </div>

          {/* CSV Export Button */}
          <button
            onClick={exportCSV}
            className="px-2.5 py-1 text-xs bg-slate-800 hover:bg-slate-750 text-slate-300 rounded border border-slate-700 flex items-center gap-1.5 transition"
            title="Export filtered dataset to CSV"
          >
            <Download className="w-3.5 h-3.5 text-emerald-400" />
            Export CSV
          </button>
        </div>
      </div>

      {/* Main Scrollable Table Area */}
      <div className="overflow-x-auto max-h-[500px] overflow-y-auto relative scrollbar-thin scrollbar-thumb-slate-700">
        <table className="w-full text-left border-collapse text-xs font-mono">
          <thead className="bg-slate-950 text-slate-400 sticky top-0 z-10 select-none shadow-sm">
            <tr role="row">
              {orderedColumns.map((col) => {
                const sortItem = sorts.find((s) => s.key === col.key);
                const isPinned = !!col.pinned;

                return (
                  <th
                    key={col.key}
                    role="columnheader"
                    style={{ width: col.width ? `${col.width}px` : "auto" }}
                    className={`p-2.5 font-semibold uppercase tracking-wider border-b border-slate-800 relative group transition-colors ${
 isPinned ? "bg-slate-950 z-20 shadow-md" : ""
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1">
                      <button
                        onClick={(e) => col.sortable !== false && handleSort(col.key, e.shiftKey)}
                        className={`flex items-center gap-1 text-left hover:text-slate-100 ${
 col.sortable === false ? "cursor-default" : "cursor-pointer"
                        }`}
                        title={col.sortable !== false ? "Click to sort (Shift+Click for multi-sort)" : ""}
                      >
                        <span>{col.header}</span>
                        {col.sortable !== false && (
                          <span className="text-slate-500">
                            {sortItem?.order === "asc" ? (
                              <ArrowUp className="w-3 h-3 text-emerald-400" />
                            ) : sortItem?.order === "desc" ? (
                              <ArrowDown className="w-3 h-3 text-emerald-400" />
                            ) : (
                              <ArrowUpDown className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                            )}
                          </span>
                        )}
                      </button>

                      {/* Pin Column Toggle */}
                      <button
                        onClick={() => togglePin(col.key)}
                        className={`p-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity hover:bg-slate-800 ${
 col.pinned ? "text-emerald-400 opacity-100" : "text-slate-500"
                        }`}
                        title={col.pinned ? `Pinned ${col.pinned}` : "Pin Column"}
                      >
                        <Pin className="w-3 h-3" />
                      </button>
                    </div>

                    {/* Resizer Handle */}
                    <div
                      onMouseDown={(e) => handleResizeStart(e, col.key, col.width)}
                      className="absolute right-0 top-0 bottom-0 w-1.5 cursor-col-resize hover:bg-emerald-500/50 group-hover:bg-slate-700/50"
                    />
                  </th>
                );
              })}
            </tr>
          </thead>

          <tbody className="divide-y divide-slate-800/60 bg-slate-900/40">
            {paginatedData.length === 0 ? (
              <tr>
                <td colSpan={orderedColumns.length} className="p-8 text-center text-slate-500 italic">
                  <div className="flex flex-col items-center gap-2">
                    <Sparkles className="w-6 h-6 text-slate-600" />
                    <span>{emptyMessage}</span>
                  </div>
                </td>
              </tr>
            ) : (
              paginatedData.map((row, idx) => {
                const key = keyExtractor(row);
                const isSelected = selectedIndex === idx;

                return (
                  <tr
                    key={key}
                    role="row"
                    onClick={() => {
                      setSelectedIndex(idx);
                      if (onRowClick) onRowClick(row);
                    }}
                    className={`hover:bg-slate-800/60 transition-colors cursor-pointer ${
 isSelected ? "bg-emerald-950/40 text-emerald-200 border-l-2 border-l-emerald-400" : ""
                    }`}
                  >
                    {orderedColumns.map((col) => {
                      const val = col.accessor(row);
                      const isPinned = !!col.pinned;

                      return (
                        <td
                          key={col.key}
                          role="gridcell"
                          className={`p-2.5 whitespace-nowrap ${
 isPinned ? "bg-slate-900 z-10" : ""
                          }`}
                        >
                          {col.cell ? col.cell(val, row) : String(val ?? "—")}
                        </td>
                      );
                    })}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      <div className="p-2.5 bg-slate-950/80 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400 font-mono">
        <div>
          Showing {sortedData.length > 0 ? (currentPage - 1) * pageSize + 1 : 0} to{" "}
          {Math.min(currentPage * pageSize, sortedData.length)} of {sortedData.length} records
          {sorts.length > 0 && (
            <span className="ml-2 text-[11px] text-emerald-400">
              (Sorted by {sorts.map((s) => `${s.key}:${s.order}`).join(", ")})
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setCurrentPage((p) => Math.max(p - 1, 1))}
            disabled={currentPage === 1}
            className="p-1 rounded bg-slate-800 hover:bg-slate-750 disabled:opacity-40 disabled:hover:bg-slate-800"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span>
            Page <strong>{currentPage}</strong> of <strong>{totalPages}</strong>
          </span>
          <button
            onClick={() => setCurrentPage((p) => Math.min(p + 1, totalPages))}
            disabled={currentPage === totalPages}
            className="p-1 rounded bg-slate-800 hover:bg-slate-750 disabled:opacity-40 disabled:hover:bg-slate-800"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
