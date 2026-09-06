import React from 'react';
import { Compass, Plus, MapPin, Trash2, LogOut, ChevronRight, Folder } from 'lucide-react';
import { getUserProfile, clearToken } from '../../services/auth';

export default function Sidebar({
  workspaces = [],
  activeWorkspaceId,
  onSelectWorkspace,
  onNewTripClick,
  onDeleteWorkspace,
  onLogout,
  isOpen = false,
  onClose,
}) {
  const profile = getUserProfile();

  const handleLogoutClick = () => {
    if (window.confirm('Bạn có chắc chắn muốn đăng xuất không?')) {
      clearToken();
      onLogout();
    }
  };

  const handleDelete = (e, wsId, wsTitle) => {
    e.stopPropagation();
    if (window.confirm(`Bạn có chắc chắn muốn xóa chuyến đi "${wsTitle}"?`)) {
      onDeleteWorkspace(wsId);
    }
  };

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpen && (
        <div
          onClick={onClose}
          className="fixed inset-0 z-40 bg-stone-900/40 backdrop-blur-xs lg:hidden"
        />
      )}

      {/* Sidebar Container */}
      <aside
        className={`fixed top-0 bottom-0 left-0 z-40 w-72 bg-surface-card border-r border-surface-border flex flex-col transition-transform duration-300 ease-in-out lg:static lg:translate-x-0 ${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Brand Header */}
        <div className="h-16 px-5 border-b border-surface-border flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-terracotta to-amber flex items-center justify-center text-white shadow-sm">
              <Compass className="w-5 h-5" />
            </div>
            <div>
              <span className="font-bold text-base text-stone-900 tracking-tight">
                Travel Agent
              </span>
              <span className="ml-1.5 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-100 text-amber-800 border border-amber-200">
                VN 🇻🇳
              </span>
            </div>
          </div>
        </div>

        {/* Action: New Trip Button */}
        <div className="p-4 border-b border-surface-border/60">
          <button
            type="button"
            onClick={onNewTripClick}
            className="w-full py-2.5 px-4 rounded-xl bg-terracotta hover:bg-terracotta-hover text-white text-sm font-semibold shadow-sm hover:shadow transition-all flex items-center justify-center gap-2 group"
          >
            <Plus className="w-4 h-4 transition-transform group-hover:rotate-90" />
            <span>Tạo chuyến đi mới</span>
          </button>
        </div>

        {/* Workspaces List Section */}
        <div className="flex-1 overflow-y-auto px-3 py-3 space-y-1">
          <div className="px-2 py-1.5 text-xs font-semibold uppercase tracking-wider text-stone-400 flex items-center justify-between">
            <span>Chuyến đi của bạn</span>
            <span className="text-[11px] font-mono bg-stone-100 px-1.5 py-0.5 rounded text-stone-600">
              {workspaces.length}
            </span>
          </div>

          {workspaces.length === 0 ? (
            <div className="p-6 text-center text-stone-400">
              <Folder className="w-8 h-8 mx-auto mb-2 opacity-40" />
              <p className="text-xs">Chưa có chuyến đi nào được tạo.</p>
            </div>
          ) : (
            workspaces.map((ws) => {
              const isActive = ws.workspace_id === activeWorkspaceId;
              return (
                <div
                  key={ws.workspace_id}
                  onClick={() => {
                    onSelectWorkspace(ws.workspace_id);
                    if (onClose) onClose();
                  }}
                  className={`group relative flex items-center justify-between p-3 rounded-xl cursor-pointer text-sm transition-all ${
                    isActive
                      ? 'bg-terracotta/10 text-terracotta font-semibold shadow-xs border border-terracotta/20'
                      : 'text-stone-700 hover:bg-surface-muted hover:text-stone-900'
                  }`}
                >
                  <div className="min-w-0 flex-1 pr-2">
                    <div className="truncate text-sm font-medium">
                      {ws.title}
                    </div>
                    {ws.destination_scope && (
                      <div className="flex items-center gap-1 text-xs text-stone-400 mt-0.5 truncate">
                        <MapPin className="w-3 h-3 shrink-0 text-teal" />
                        <span className="truncate">{ws.destination_scope}</span>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      type="button"
                      title="Xóa chuyến đi"
                      onClick={(e) => handleDelete(e, ws.workspace_id, ws.title)}
                      className="p-1 rounded text-stone-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                    <ChevronRight className="w-3.5 h-3.5 text-stone-400" />
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* User Profile & Logout Footer */}
        <div className="p-3 border-t border-surface-border bg-surface-muted/40">
          <div className="flex items-center justify-between p-2 rounded-xl bg-surface-card border border-surface-border">
            <div className="min-w-0 flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-terracotta/15 text-terracotta font-bold text-xs flex items-center justify-center shrink-0">
                {profile.name ? profile.name.charAt(0).toUpperCase() : 'U'}
              </div>
              <div className="min-w-0">
                <div className="text-xs font-semibold text-stone-800 truncate">
                  {profile.name}
                </div>
                <div className="text-[10px] text-stone-400 font-mono truncate">
                  {profile.token ? `${profile.token.slice(0, 12)}...` : 'Unbound'}
                </div>
              </div>
            </div>

            <button
              type="button"
              onClick={handleLogoutClick}
              title="Đăng xuất"
              className="p-1.5 rounded-lg text-stone-400 hover:text-stone-700 hover:bg-stone-100 transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
