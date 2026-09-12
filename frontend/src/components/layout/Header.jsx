import React from 'react';
import { PanelLeftOpen, LogOut } from 'lucide-react';
import { getUserProfile } from '../../services/auth';

export default function Header({
  onToggleSidebar,
  onLogout,
}) {
  const profile = getUserProfile();

  return (
    <header className="h-14 px-4 sm:px-6 bg-pure-white flex items-center justify-between shrink-0 font-sans z-10 relative">
      {/* Skip Link for Screen Readers & Keyboard Navigation */}
      <a
        href="#chat-main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-4 focus:z-50 focus:px-3 focus:py-1 focus:bg-ink-press focus:text-pure-white focus:rounded-lg focus:text-caption focus:font-medium focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none"
      >
        Chuyển đến nội dung chính
      </a>

      {/* Left section: Mobile menu drawer button only */}
      <div className="flex items-center min-w-0">
        <button
          type="button"
          onClick={onToggleSidebar}
          aria-label="Mở thanh bên"
          className="p-2 rounded-lg text-graphite-ink hover:bg-hover-veil transition-colors lg:hidden focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none cursor-pointer"
          title="Mở thanh bên"
        >
          <PanelLeftOpen className="w-5 h-5 stroke-[1.8]" aria-hidden="true" />
        </button>
      </div>

      {/* Right section: User profile & Logout for authenticated users */}
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-2.5">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full bg-graphite-ink text-pure-white font-medium text-caption flex items-center justify-center shrink-0 select-none">
              {profile.name ? profile.name.charAt(0).toUpperCase() : 'U'}
            </div>
            <span className="text-caption font-medium text-graphite-ink hidden sm:inline">
              {profile.name || 'Người dùng'}
            </span>
          </div>
          {onLogout && (
            <button
              type="button"
              onClick={onLogout}
              aria-label="Đăng xuất"
              title="Đăng xuất"
              className="p-1.5 rounded-lg text-mid-ash hover:text-graphite-ink hover:bg-hover-veil transition-colors focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none cursor-pointer"
            >
              <LogOut className="w-4 h-4 stroke-[1.8]" aria-hidden="true" />
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
