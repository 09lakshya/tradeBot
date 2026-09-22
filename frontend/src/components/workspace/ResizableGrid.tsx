"use client";

import React, { useState } from "react";
import { useWorkspaceStore, WidgetConfig } from "@/stores/useWorkspaceStore";
import { Move, Maximize2, Minimize2, EyeOff } from "lucide-react";

interface ResizableGridProps {
  renderWidget: (widgetId: string) => React.ReactNode;
}

export function ResizableGrid({ renderWidget }: ResizableGridProps) {
  const { workspaces, activeWorkspaceId, isEditMode, reorderWidgets, toggleWidgetVisibility } = useWorkspaceStore();
  const activeWs = workspaces.find((w) => w.id === activeWorkspaceId) || workspaces[0];

  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);

  if (!activeWs) return null;

  const visibleWidgets = activeWs.widgets.filter((w) => w.visible);

  const handleDragStart = (index: number) => {
    setDraggedIndex(index);
  };

  const handleDragOver = (e: React.DragEvent, targetIndex: number) => {
    e.preventDefault();
    if (draggedIndex === null || draggedIndex === targetIndex) return;

    const newWidgets = [...activeWs.widgets];
    const [movedItem] = newWidgets.splice(draggedIndex, 1);
    newWidgets.splice(targetIndex, 0, movedItem);

    setDraggedIndex(targetIndex);
    reorderWidgets(activeWorkspaceId, newWidgets);
  };

  const handleDragEnd = () => {
    setDraggedIndex(null);
  };

  // Rows size to their content: `auto-rows-fr` made every row as tall as the
  // tallest widget (the chart), stretching short cards into blank space.
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
      {visibleWidgets.map((widget, index) => {
        const isFullWidth = widget.colSpan === 2;

        return (
          <div
            key={widget.id}
            draggable={isEditMode}
            onDragStart={() => handleDragStart(index)}
            onDragOver={(e) => handleDragOver(e, index)}
            onDragEnd={handleDragEnd}
            className={`relative transition-all ${isFullWidth ? "lg:col-span-2" : "lg:col-span-1"} ${
              isEditMode
                ? "border-2 border-dashed border-emerald-500/50 bg-slate-900/60 p-2 rounded-lg cursor-grab active:cursor-grabbing"
                : ""
            } ${draggedIndex === index ? "opacity-40 scale-[0.99]" : ""}`}
          >
            {isEditMode && (
              <div className="absolute top-3 right-3 z-20 flex items-center gap-2 bg-slate-950/90 border border-slate-700 px-2 py-1 rounded shadow-lg">
                <span className="text-[11px] font-mono text-emerald-400 flex items-center gap-1">
                  <Move className="w-3 h-3" />
                  Drag to move
                </span>
                <button
                  onClick={() => toggleWidgetVisibility(activeWorkspaceId, widget.id)}
                  className="text-slate-400 hover:text-rose-400 p-0.5"
                  title="Hide Widget"
                >
                  <EyeOff className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
            {renderWidget(widget.id)}
          </div>
        );
      })}
    </div>
  );
}
