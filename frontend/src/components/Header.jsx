import React from 'react';

export default function Header({ onToggleSidebar }) {
  return (
    <header className="sticky top-0 w-full h-14 px-4 flex justify-between items-center bg-[#212121] border-b border-[#2f2f2f] z-40">
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleSidebar}
          className="p-2 text-gray-400 hover:text-white transition-colors md:hidden"
        >
          <span className="material-symbols-outlined">menu</span>
        </button>
        <div className="flex items-center gap-2 bg-[#2f2f2f] px-3 py-1.5 rounded-lg border border-[#424242] cursor-pointer hover:bg-[#383838]">
          <span className="text-sm font-semibold text-white">ChatGPT 4o-mini</span>
          <span className="material-symbols-outlined text-gray-400 text-sm">expand_more</span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-[#10a37f]/20 text-[#10a37f] border border-[#10a37f]/30">
          <span className="w-2 h-2 rounded-full bg-[#10a37f] animate-pulse"></span>
          FastAPI Online
        </span>
      </div>
    </header>
  );
}
