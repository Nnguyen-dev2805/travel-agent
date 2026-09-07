import React, { useState } from 'react';
import {
  Compass,
  SquarePen,
  Trash2,
  LogOut,
  Settings,
  HelpCircle,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  MessageSquare,
} from 'lucide-react';
import { getUserProfile, clearToken } from '../../services/auth';

export default function Sidebar({
  workspaces = [],
  activeWorkspaceId,
  onSelectWorkspace,
  onNewTripClick,
  onDeleteWorkspace,
  onLogout,
  onLoginClick,
  isOpen = false,
  onClose,
  isCollapsed = false,
  onToggleCollapse,
}) {
  const profile = getUserProfile();
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearchOpen, setIsSearchOpen] = useState(false);

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

  const filteredWorkspaces = searchQuery.trim()
    ? workspaces.filter((ws) =>
        ws.title.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : workspaces;

  // Render the full expanded sidebar content
  const renderFullSidebar = () => (
    <div className="w-[260px] h-full flex flex-col shrink-0 overflow-hidden">
      {/* Brand Header Strip: Logo on left, Collapse button on right */}
      <div className="h-[52px] px-3.5 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2 text-graphite-ink">
          <div className="w-6 h-6 rounded-md bg-graphite-ink text-pure-white flex items-center justify-center">
            <Compass className="w-4 h-4 stroke-[2]" aria-hidden="true" />
          </div>
          <span className="font-semibold text-[15px] tracking-tight text-graphite-ink">
            Travel Agent
          </span>
        </div>

        <button
          type="button"
          onClick={() => {
            if (window.innerWidth < 1024) {
              if (onClose) onClose();
            } else {
              if (onToggleCollapse) onToggleCollapse();
            }
          }}
          aria-label="Thu gọn thanh bên"
          title="Thu gọn"
          className="p-1.5 rounded-lg text-mid-ash hover:text-graphite-ink hover:bg-hover-veil transition-colors focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none cursor-pointer"
        >
          <PanelLeftClose className="w-4 h-4 stroke-[1.8]" aria-hidden="true" />
        </button>
      </div>

      {/* Action: New Chat & Search */}
      <div className="px-2 pt-1 pb-2 space-y-1 shrink-0">
        <button
          type="button"
          onClick={onNewTripClick}
          className="w-full py-2 px-2.5 rounded-lg hover:bg-hover-veil text-graphite-ink text-caption font-medium transition-colors flex items-center justify-between group focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none cursor-pointer"
        >
          <div className="flex items-center gap-2.5">
            <SquarePen className="w-4 h-4 stroke-[1.8] text-graphite-ink" aria-hidden="true" />
            <span>Chuyến đi mới</span>
          </div>
          <span className="text-[11px] text-hollow font-mono">⌘K</span>
        </button>

        {/* Search Chats Row */}
        {workspaces.length > 0 && (
          <button
            type="button"
            onClick={() => setIsSearchOpen((prev) => !prev)}
            className="w-full py-2 px-2.5 rounded-lg hover:bg-hover-veil text-graphite-ink text-caption font-medium transition-colors flex items-center gap-2.5 group focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none cursor-pointer"
          >
            <Search className="w-4 h-4 stroke-[1.8] text-graphite-ink" aria-hidden="true" />
            <span>Tìm chuyến đi</span>
          </button>
        )}

        {isSearchOpen && (
          <div className="px-1 pt-1">
            <input
              type="text"
              autoFocus
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Tìm kiếm..."
              className="w-full px-2.5 py-1.5 rounded-lg border border-hairline bg-pure-white text-caption text-graphite-ink placeholder-hollow focus:outline-none focus:ring-1 focus:ring-graphite-ink"
            />
          </div>
        )}
      </div>

      {/* Workspaces / Chat History List */}
      <div className="flex-1 overflow-y-auto px-2 py-1 space-y-0.5">
        {workspaces.length > 0 && (
          <div className="px-2.5 py-1.5 text-[11px] font-medium text-hollow flex items-center justify-between select-none">
            <span>Gần đây</span>
          </div>
        )}

        {filteredWorkspaces.length === 0 ? (
          <div className="p-4 text-center text-hollow text-caption">
            {searchQuery ? 'Không tìm thấy chuyến đi nào' : 'Chưa có chuyến đi nào'}
          </div>
        ) : (
          filteredWorkspaces.map((ws) => {
            const isActive = ws.workspace_id === activeWorkspaceId;
            return (
              <button
                type="button"
                key={ws.workspace_id}
                aria-current={isActive ? 'page' : undefined}
                onClick={() => {
                  onSelectWorkspace(ws.workspace_id);
                  if (onClose) onClose();
                }}
                className={`w-full text-left group relative flex items-center justify-between px-2.5 py-2 rounded-lg text-caption transition-colors focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none cursor-pointer ${
                  isActive
                    ? 'bg-hover-veil text-graphite-ink font-medium'
                    : 'text-graphite-ink hover:bg-hover-veil'
                }`}
              >
                <div className="min-w-0 flex-1 pr-2">
                  <div className="truncate text-caption leading-snug">
                    {ws.title}
                  </div>
                </div>

                <div className="opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    type="button"
                    aria-label={`Xóa chuyến đi "${ws.title}"`}
                    title="Xóa chuyến đi"
                    onClick={(e) => handleDelete(e, ws.workspace_id, ws.title)}
                    className="p-1 rounded text-mid-ash hover:text-graphite-ink hover:bg-hover-veil transition-colors focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none"
                  >
                    <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
                  </button>
                </div>
              </button>
            );
          })
        )}
      </div>

      {/* Sidebar Footer Block */}
      <div className="p-2 border-t border-hairline space-y-1 shrink-0">
        <button
          type="button"
          className="w-full py-2 px-2.5 rounded-lg hover:bg-hover-veil text-graphite-ink text-caption font-medium transition-colors flex items-center gap-2.5 focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none cursor-pointer"
        >
          <Settings className="w-4 h-4 stroke-[1.8] text-graphite-ink" aria-hidden="true" />
          <span>Cài đặt</span>
        </button>

        <button
          type="button"
          className="w-full py-2 px-2.5 rounded-lg hover:bg-hover-veil text-graphite-ink text-caption font-medium transition-colors flex items-center gap-2.5 focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none cursor-pointer"
        >
          <HelpCircle className="w-4 h-4 stroke-[1.8] text-graphite-ink" aria-hidden="true" />
          <span>Trợ giúp</span>
        </button>

        {/* User Account / Profile Row */}
        {profile.token ? (
          <div className="pt-1 mt-1 border-t border-hairline flex items-center justify-between p-1.5 rounded-lg">
            <div className="min-w-0 flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-full bg-graphite-ink text-pure-white font-medium text-caption flex items-center justify-center shrink-0 select-none">
                {profile.name ? profile.name.charAt(0).toUpperCase() : 'A'}
              </div>
              <div className="min-w-0" title={profile.name || 'Người dùng'}>
                <div className="text-caption font-medium text-graphite-ink truncate leading-tight">
                  {profile.name || 'Alice'}
                </div>
              </div>
            </div>

            <button
              type="button"
              onClick={handleLogoutClick}
              aria-label="Đăng xuất tài khoản"
              title="Đăng xuất"
              className="p-1.5 rounded-lg text-mid-ash hover:text-graphite-ink hover:bg-hover-veil transition-colors focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none cursor-pointer"
            >
              <LogOut className="w-4 h-4 stroke-[1.8]" aria-hidden="true" />
            </button>
          </div>
        ) : (
          <div className="p-3 bg-pure-white rounded-lg border border-hairline space-y-2 mt-1">
            <div className="font-semibold text-caption text-graphite-ink leading-snug">
              Cá nhân hóa trải nghiệm
            </div>
            <p className="text-[12px] text-mid-ash leading-snug">
              Đăng nhập để lưu lịch trình và đồng bộ các chuyến đi của bạn.
            </p>
            <button
              type="button"
              onClick={onLoginClick}
              className="w-full py-1.5 px-3 rounded-full bg-pure-white border border-hairline text-caption font-medium text-graphite-ink hover:bg-hover-veil transition-colors focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none cursor-pointer"
            >
              Đăng nhập
            </button>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpen && (
        <div
          onClick={onClose}
          className="fixed inset-0 z-40 bg-deep-charcoal lg:hidden"
        />
      )}

      {/* Sidebar Container: 260px wide when expanded, 56px wide rail when collapsed on desktop */}
      <aside
        className={`h-full fixed top-0 bottom-0 left-0 z-40 bg-sidebar-mist border-r border-hairline flex flex-col font-sans transition-all duration-200 ease-in-out select-none overflow-hidden ${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        } ${
          isCollapsed
            ? 'w-[260px] lg:static lg:translate-x-0 lg:w-[56px] lg:min-w-[56px]'
            : 'w-[260px] lg:static lg:translate-x-0 lg:w-[260px] lg:min-w-[260px]'
        }`}
      >
        {/* If isCollapsed on desktop, render the narrow icon rail (Image 1 from ChatGPT) */}
        {isCollapsed ? (
          <>
            {/* Desktop Icon Rail (w-full fills the 56px aside) */}
            <div className="hidden lg:flex flex-col justify-between items-center h-full py-4 w-full">
              {/* Top Action Icons */}
              <div className="flex flex-col items-center gap-3">
                {/* Logo / Expand Trigger */}
                <button
                  type="button"
                  onClick={onToggleCollapse}
                  aria-label="Mở thanh bên"
                  title="Mở thanh bên"
                  className="w-9 h-9 rounded-lg flex items-center justify-center text-graphite-ink hover:bg-hover-veil transition-colors focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none group relative cursor-pointer"
                >
                  <div className="w-6 h-6 rounded-md bg-graphite-ink text-pure-white flex items-center justify-center group-hover:hidden transition-all">
                    <Compass className="w-4 h-4 stroke-[2]" aria-hidden="true" />
                  </div>
                  <PanelLeftOpen className="w-5 h-5 stroke-[1.8] text-graphite-ink hidden group-hover:block transition-all" aria-hidden="true" />
                </button>

                {/* New Chat Button (SquarePen matching Image 1) */}
                <button
                  type="button"
                  onClick={onNewTripClick}
                  aria-label="Chuyến đi mới (⌘K)"
                  title="Chuyến đi mới (⌘K)"
                  className="w-9 h-9 rounded-lg flex items-center justify-center text-graphite-ink hover:bg-hover-veil transition-colors focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none cursor-pointer"
                >
                  <SquarePen className="w-[18px] h-[18px] stroke-[1.8]" aria-hidden="true" />
                </button>

                {/* Search Chats Button */}
                <button
                  type="button"
                  onClick={() => {
                    if (onToggleCollapse) onToggleCollapse();
                    setIsSearchOpen(true);
                  }}
                  aria-label="Tìm chuyến đi"
                  title="Tìm chuyến đi"
                  className="w-9 h-9 rounded-lg flex items-center justify-center text-graphite-ink hover:bg-hover-veil transition-colors focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none cursor-pointer"
                >
                  <Search className="w-[18px] h-[18px] stroke-[1.8]" aria-hidden="true" />
                </button>

                {/* Conversations History Button */}
                <button
                  type="button"
                  onClick={onToggleCollapse}
                  aria-label="Danh sách chuyến đi"
                  title="Danh sách chuyến đi"
                  className="w-9 h-9 rounded-lg flex items-center justify-center text-graphite-ink hover:bg-hover-veil transition-colors focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none cursor-pointer"
                >
                  <MessageSquare className="w-[18px] h-[18px] stroke-[1.8]" aria-hidden="true" />
                </button>
              </div>

              {/* Bottom User Avatar (matching PD in Image 1) */}
              <div className="flex flex-col items-center">
                {profile.token ? (
                  <button
                    type="button"
                    onClick={handleLogoutClick}
                    aria-label={`Tài khoản ${profile.name || 'Alice'}. Nhấn để đăng xuất.`}
                    title={`${profile.name || 'Alice'} (Đăng xuất)`}
                    className="w-8 h-8 rounded-full bg-graphite-ink text-pure-white font-medium text-[13px] flex items-center justify-center hover:opacity-85 transition-opacity focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none cursor-pointer"
                  >
                    {profile.name ? profile.name.charAt(0).toUpperCase() : 'A'}
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={onLoginClick}
                    aria-label="Đăng nhập"
                    title="Đăng nhập"
                    className="w-8 h-8 rounded-full border border-hairline bg-pure-white text-graphite-ink flex items-center justify-center hover:bg-hover-veil transition-colors cursor-pointer"
                  >
                    <Compass className="w-4 h-4 stroke-[1.8]" />
                  </button>
                )}
              </div>
            </div>

            {/* Mobile drawer (if opened on mobile viewport) */}
            <div className="flex lg:hidden h-full">
              {renderFullSidebar()}
            </div>
          </>
        ) : (
          renderFullSidebar()
        )}
      </aside>
    </>
  );
}
