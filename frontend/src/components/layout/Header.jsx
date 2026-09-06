import React from 'react';
import { Menu, MessageSquare, Calendar, MapPin, Compass } from 'lucide-react';

export default function Header({
  activeWorkspace,
  mobileActiveTab,
  onMobileTabChange,
  onToggleSidebar,
}) {
  return (
    <header className="h-16 px-4 lg:px-6 bg-surface-card border-b border-surface-border flex items-center justify-between shrink-0">
      {/* Left section: Hamburger button & Workspace metadata */}
      <div className="flex items-center gap-3 min-w-0">
        <button
          type="button"
          onClick={onToggleSidebar}
          className="p-2 rounded-lg text-stone-600 hover:bg-surface-muted lg:hidden"
          title="Mở menu danh sách chuyến đi"
        >
          <Menu className="w-5 h-5" />
        </button>

        {activeWorkspace ? (
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold text-stone-900 truncate">
                {activeWorkspace.title}
              </h1>
              {activeWorkspace.planning_status && (
                <span className="hidden sm:inline-flex px-2 py-0.5 rounded-full text-[11px] font-semibold bg-teal/10 text-teal border border-teal/20 capitalize">
                  {activeWorkspace.planning_status}
                </span>
              )}
            </div>
            {activeWorkspace.destination_scope && (
              <div className="flex items-center gap-1 text-xs text-stone-500 truncate">
                <MapPin className="w-3 h-3 text-terracotta shrink-0" />
                <span className="truncate">{activeWorkspace.destination_scope}</span>
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <Compass className="w-5 h-5 text-terracotta" />
            <span className="text-sm font-semibold text-stone-800">
              Chưa chọn chuyến đi
            </span>
          </div>
        )}
      </div>

      {/* Center/Right section: Mobile Tab Switcher (Visible only on < lg) */}
      {activeWorkspace && (
        <div className="flex items-center lg:hidden">
          <div className="flex p-1 rounded-xl bg-surface-muted border border-surface-border">
            <button
              type="button"
              onClick={() => onMobileTabChange('chat')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                mobileActiveTab === 'chat'
                  ? 'bg-surface-card text-terracotta shadow-xs'
                  : 'text-stone-600 hover:text-stone-900'
              }`}
            >
              <MessageSquare className="w-3.5 h-3.5" />
              <span>Trò chuyện</span>
            </button>

            <button
              type="button"
              onClick={() => onMobileTabChange('planner')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                mobileActiveTab === 'planner'
                  ? 'bg-surface-card text-terracotta shadow-xs'
                  : 'text-stone-600 hover:text-stone-900'
              }`}
            >
              <Calendar className="w-3.5 h-3.5" />
              <span>Lịch trình</span>
            </button>
          </div>
        </div>
      )}
    </header>
  );
}
