import React from 'react';

export default function Header({ onToggleSidebar, currentUser, onOpenAuthModal, onLogout }) {
  return (
    <header className="md:hidden w-full flex items-center justify-between p-4 bg-[#212121] sticky top-0 z-40 border-b border-[#3d3d3d]">
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleSidebar}
          className="p-1 text-gray-400 hover:text-white transition-colors"
        >
          <span className="material-symbols-outlined">menu</span>
        </button>
        <h1 className="text-base font-medium text-white">VietraAI</h1>
      </div>

      <div className="flex items-center gap-3">
        {currentUser ? (
          <button
            onClick={onLogout}
            className="px-3 py-1 rounded-lg text-xs font-medium bg-[#2f2f2f] hover:bg-red-500/20 text-gray-300 hover:text-red-400 border border-[#3d3d3d] transition-all"
          >
            Sign out
          </button>
        ) : (
          <button
            onClick={onOpenAuthModal}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-[#10a37f] hover:bg-[#12a480] text-white transition-all shadow-sm"
          >
            <span className="material-symbols-outlined text-sm">login</span>
            <span>Sign in</span>
          </button>
        )}
      </div>
    </header>
  );
}
