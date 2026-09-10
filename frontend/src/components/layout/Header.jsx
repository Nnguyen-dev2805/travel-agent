import React from 'react';
import { PanelLeftOpen } from 'lucide-react';
import { isAuthenticated } from '../../services/auth';

export default function Header({
  onToggleSidebar,
  onLoginClick,
  onMemoryClick,
}) {
  const isAuth = isAuthenticated();

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

      {/* Right section: Pill Actions matching ChatGPT reference */}
      <div className="flex items-center gap-2">
        {onMemoryClick && (
          <button
            id="memory-manager-toggle"
            type="button"
            onClick={onMemoryClick}
            className="px-3.5 py-1.5 rounded-full bg-pure-white border border-hairline hover:bg-hover-veil text-graphite-ink text-caption font-medium transition-colors focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none cursor-pointer"
          >
            Memory
          </button>
        )}
        {!isAuth && (
          <>
            <button
              type="button"
              onClick={onLoginClick}
              className="px-3.5 py-1.5 rounded-full bg-graphite-ink hover:bg-black text-pure-white text-caption font-medium transition-colors focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none cursor-pointer"
            >
              Đăng nhập
            </button>
            <button
              type="button"
              onClick={onLoginClick}
              className="px-3.5 py-1.5 rounded-full bg-pure-white border border-hairline hover:bg-hover-veil text-graphite-ink text-caption font-medium transition-colors focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none cursor-pointer"
            >
              Đăng ký miễn phí
            </button>
          </>
        )}
      </div>
    </header>
  );
}
