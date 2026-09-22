"use client";

import React, { useState, useRef } from "react";
import { useWorkspaceStore } from "@/stores/useWorkspaceStore";
import { Layout, Save, Download, Upload, Trash2, Edit3, Check, Plus, RefreshCw, Eye, EyeOff } from "lucide-react";

export function WorkspaceManager() {
  const {
    workspaces,
    activeWorkspaceId,
    setActiveWorkspace,
    isEditMode,
    toggleEditMode,
    saveCurrentAsCustom,
    deleteWorkspace,
    exportLayoutJSON,
    importLayoutJSON,
    resetToDefaults,
    toggleWidgetVisibility,
  } = useWorkspaceStore();

  const [newLayoutName, setNewLayoutName] = useState("");
  const [isSavingModalOpen, setIsSavingModalOpen] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const activeWs = workspaces.find((w) => w.id === activeWorkspaceId) || workspaces[0];

  const handleSaveAsCustom = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newLayoutName.trim()) return;
    saveCurrentAsCustom(newLayoutName.trim());
    setNewLayoutName("");
    setIsSavingModalOpen(false);
  };

  const handleExport = () => {
    const json = exportLayoutJSON(activeWorkspaceId);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `workspace-layout-${activeWs.name.toLowerCase().replace(/\s+/g, "-")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImportFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      const success = importLayoutJSON(content);
      if (!success) {
        setImportError("Invalid workspace layout JSON file format.");
        setTimeout(() => setImportError(null), 4000);
      }
    };
    reader.readAsText(file);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-lg p-3 mb-4 ">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Workspace Selector */}
        <div className="flex items-center gap-2">
          <Layout className="w-4 h-4 text-emerald-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Workspace:</span>

          <div className="flex items-center gap-1.5 flex-wrap">
            {workspaces.map((ws) => (
              <button
                key={ws.id}
                onClick={() => setActiveWorkspace(ws.id)}
                className={`px-3 py-1 text-xs rounded-md font-medium transition-all flex items-center gap-1.5 ${
 ws.id === activeWorkspaceId
                    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm shadow-emerald-950"
                    : "bg-slate-800/80 text-slate-300 hover:bg-slate-800 border border-slate-700/60"
                }`}
              >
                <span>{ws.name}</span>
                {!ws.isPreset && (
                  <span
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteWorkspace(ws.id);
                    }}
                    className="text-slate-400 hover:text-rose-400 p-0.5 rounded"
                    title="Delete layout"
                  >
                    <Trash2 className="w-3 h-3" />
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Toolbar Actions */}
        <div className="flex items-center gap-2">
          {/* Widget Visibility Toggles in Edit Mode */}
          {isEditMode && activeWs && (
            <div className="flex items-center gap-1 bg-slate-950 px-2 py-1 rounded border border-slate-800">
              <span className="text-[10px] uppercase font-mono text-slate-500 mr-1">Panels:</span>
              {activeWs.widgets.map((widget) => (
                <button
                  key={widget.id}
                  onClick={() => toggleWidgetVisibility(activeWorkspaceId, widget.id)}
                  className={`px-1.5 py-0.5 text-[11px] rounded flex items-center gap-1 border ${
 widget.visible
                      ? "bg-emerald-950/60 border-emerald-800 text-emerald-300"
                      : "bg-slate-900 border-slate-800 text-slate-500 line-through"
                  }`}
                  title={`Toggle ${widget.title}`}
                >
                  {widget.visible ? <Eye className="w-2.5 h-2.5" /> : <EyeOff className="w-2.5 h-2.5" />}
                  {widget.title.split(" ")[0]}
                </button>
              ))}
            </div>
          )}

          <button
            onClick={toggleEditMode}
            className={`px-2.5 py-1 text-xs rounded font-medium flex items-center gap-1.5 border transition ${
 isEditMode
                ? "bg-amber-500/20 text-amber-300 border-amber-500/50 animate-pulse"
                : "bg-slate-800 text-slate-300 hover:bg-slate-750 border-slate-700"
            }`}
          >
            {isEditMode ? <Check className="w-3.5 h-3.5" /> : <Edit3 className="w-3.5 h-3.5" />}
            {isEditMode ? "Done Editing" : "Edit Layout"}
          </button>

          <button
            onClick={() => setIsSavingModalOpen(true)}
            className="px-2.5 py-1 text-xs rounded font-medium bg-slate-800 text-slate-300 hover:bg-slate-750 border border-slate-700 flex items-center gap-1.5"
            title="Save layout preset"
          >
            <Save className="w-3.5 h-3.5 text-cyan-400" />
            Save Preset
          </button>

          <button
            onClick={handleExport}
            className="px-2 py-1 text-xs rounded bg-slate-800 text-slate-300 hover:bg-slate-750 border border-slate-700 flex items-center gap-1"
            title="Export layout as JSON"
          >
            <Download className="w-3.5 h-3.5 text-emerald-400" />
            Export
          </button>

          <button
            onClick={() => fileInputRef.current?.click()}
            className="px-2 py-1 text-xs rounded bg-slate-800 text-slate-300 hover:bg-slate-750 border border-slate-700 flex items-center gap-1"
            title="Import layout from JSON"
          >
            <Upload className="w-3.5 h-3.5 text-purple-400" />
            Import
          </button>

          <button
            onClick={resetToDefaults}
            className="p-1 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded border border-transparent hover:border-slate-700"
            title="Reset to default workspace presets"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>

          <input
            type="file"
            ref={fileInputRef}
            onChange={handleImportFile}
            accept=".json"
            className="hidden"
          />
        </div>
      </div>

      {importError && (
        <div className="mt-2 text-xs text-rose-400 bg-rose-950/50 border border-rose-800 p-2 rounded">
          {importError}
        </div>
      )}

      {/* Save Layout Modal */}
      {isSavingModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 w-full max-w-md shadow-2xl">
            <h3 className="text-base font-semibold text-slate-100 mb-2 flex items-center gap-2">
              <Save className="w-4 h-4 text-emerald-400" />
              Save Custom Workspace Layout
            </h3>
            <p className="text-xs text-slate-400 mb-4">
              Enter a name for your custom dashboard preset layout.
            </p>
            <form onSubmit={handleSaveAsCustom}>
              <input
                type="text"
                value={newLayoutName}
                onChange={(e) => setNewLayoutName(e.target.value)}
                placeholder="e.g., High-Volatility Scalping"
                autoFocus
                className="w-full bg-slate-950 border border-slate-700 rounded p-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500 mb-4"
              />
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsSavingModalOpen(false)}
                  className="px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200 bg-slate-800 rounded"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!newLayoutName.trim()}
                  className="px-4 py-1.5 text-xs bg-emerald-600 hover:bg-emerald-500 text-white rounded font-medium disabled:opacity-50"
                >
                  Save Preset
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
