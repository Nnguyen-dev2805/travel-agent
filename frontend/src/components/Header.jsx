import React from 'react';

export default function Header({ onToggleSidebar, currentUser, onOpenAuthModal, onLogout }) {
  return (
    <header className="sticky top-0 w-full h-14 px-4 flex justify-between items-center bg-[#212121]/90 backdrop-blur-md border-b border-[#2f2f2f] z-40">
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleSidebar}
          className="p-2 text-gray-400 hover:text-white transition-colors md:hidden"
        >
          <span className="material-symbols-outlined">menu</span>
        </button>

        {/* Model & Agent Badge */}
        <div className="flex items-center gap-2 bg-[#2f2f2f] px-3 py-1.5 rounded-xl border border-[#424242] hover:border-[#10a37f] transition-all cursor-pointer">
          <span className="w-2 h-2 rounded-full bg-[#10a37f]"></span>
          <span className="text-xs font-semibold text-white tracking-wide">
            Vietnam Travel Agent RAG
          </span>
          <span className="text-[10px] text-gray-400 font-mono bg-[#171717] px-1.5 py-0.5 rounded border border-[#383838]">
            GPT-4o-mini
          </span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {/* RAG Active Badge */}
        <span className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-[#10a37f]/15 text-[#10a37f] border border-[#10a37f]/30 shadow-sm">
          <span className="w-2 h-2 rounded-full bg-[#10a37f] animate-pulse"></span>
          RAG Vector Search Active
        </span>

        {/* Auth State & Memory Badge */}
        {currentUser ? (
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-purple-500/15 text-purple-300 border border-purple-500/30">
              <span className="material-symbols-outlined text-xs">memory</span>
              Long-term Memory
            </span>
            <button
              onClick={onLogout}
              className="px-3 py-1.5 rounded-xl text-xs font-semibold bg-[#2f2f2f] hover:bg-red-500/20 text-gray-300 hover:text-red-400 border border-[#383838] transition-all"
            >
              Đăng xuất
            </button>
          </div>
        ) : (
          <button
            onClick={onOpenAuthModal}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-[#10a37f] hover:bg-[#1a7f64] text-white transition-all shadow-md shadow-[#10a37f]/20"
          >
            <span className="material-symbols-outlined text-sm">login</span>
            <span>Đăng nhập</span>
          </button>
        )}
      </div>
    </header>
  );
}
