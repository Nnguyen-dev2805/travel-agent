import React from 'react';
import { ChevronDown } from 'lucide-react';

export default function Header({ isSidebarOpen, onToggleSidebar, currentUser, onOpenAuthModal, onLogout }) {
  return (
    <header className="w-full flex items-center justify-between px-4 md:px-6 py-3 bg-[#ffffff] sticky top-0 z-40">
      {/* Left side: Brand/Model Selector Pill */}
      <div className="flex items-center gap-2">
        <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl hover:bg-[#0000000d] transition-colors cursor-pointer group">
          <span className="text-base font-semibold text-[#0d0d0d] tracking-tight">VietraAI</span>
          <ChevronDown className="w-4 h-4 text-[#8f8f8f] group-hover:text-[#0d0d0d] stroke-[1.75]" />
        </button>
      </div>

      {/* Right side: Auth Action Pills (Only when logged out) */}
      <div className="flex items-center gap-2">
        {!currentUser && (
          <>
            <button
              onClick={onOpenAuthModal}
              className="px-4 py-1.5 rounded-full text-sm font-medium bg-[#0d0d0d] text-white hover:bg-[#000000] transition-colors cursor-pointer"
            >
              Log in
            </button>
            <button
              onClick={onOpenAuthModal}
              className="hidden sm:inline-flex px-4 py-1.5 rounded-full text-sm font-medium bg-[#ffffff] text-[#0d0d0d] border border-[#0000001a] hover:bg-[#0000000d] transition-colors cursor-pointer"
            >
              Sign up for free
            </button>
          </>
        )}
      </div>
    </header>
  );
}
