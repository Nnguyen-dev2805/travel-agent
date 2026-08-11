import React, { useState } from 'react';

export default function Sidebar({
  onNewChat,
  isOpen,
  currentUser,
  onOpenAuthModal,
  onOpenFactsModal,
  onLogout,
}) {
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);

  const handleUserClick = () => {
    if (currentUser) {
      setIsUserMenuOpen(!isUserMenuOpen);
    } else {
      onOpenAuthModal();
    }
  };

  return (
    <aside
      className={`fixed left-0 top-0 h-full w-[260px] bg-[#171717] text-white flex flex-col p-4 z-50 transition-transform duration-300 ${
        isOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
      }`}
    >
      {/* Brand Header */}
      <div className="mb-8">
        <h1 className="font-bold text-xl text-white leading-tight">VietraAI</h1>
        <p className="text-xs text-[#9e9e9e] mt-0.5">Vietnam Travel Assistant</p>
      </div>

      {/* Navigation Links */}
      <ul className="flex flex-col gap-2 flex-grow">
        <li>
          <button
            onClick={onNewChat}
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-[#303633] text-white font-medium cursor-pointer active:scale-95 transition-colors duration-200 w-full text-left"
          >
            <span className="material-symbols-outlined text-[20px]">add</span>
            <span className="text-sm">New Chat</span>
          </button>
        </li>
        <li>
          <button
            onClick={onNewChat}
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-[#dee4df] hover:bg-[#252b28] transition-colors duration-200 cursor-pointer active:scale-95 w-full text-left"
          >
            <span className="material-symbols-outlined text-[20px]">history</span>
            <span className="text-sm">History</span>
          </button>
        </li>
        <li>
          <button
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-[#dee4df] hover:bg-[#252b28] transition-colors duration-200 cursor-pointer active:scale-95 w-full text-left"
          >
            <span className="material-symbols-outlined text-[20px]">settings</span>
            <span className="text-sm">Settings</span>
          </button>
        </li>
        <li>
          <button
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-[#dee4df] hover:bg-[#252b28] transition-colors duration-200 cursor-pointer active:scale-95 w-full text-left"
          >
            <span className="material-symbols-outlined text-[20px]">help</span>
            <span className="text-sm">Help</span>
          </button>
        </li>
      </ul>

      {/* Popover Account Menu (Only Sign Out) */}
      {isUserMenuOpen && currentUser && (
        <div className="absolute bottom-16 left-3 right-3 bg-[#252b28] border border-[#3d3d3d] rounded-xl shadow-2xl p-1.5 flex flex-col gap-1 z-50 animate-in fade-in slide-in-from-bottom-2 duration-150">
          <button
            onClick={() => {
              setIsUserMenuOpen(false);
              onLogout();
            }}
            className="flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-xs font-medium text-red-400 hover:bg-red-500/15 transition-colors text-left"
          >
            <span className="material-symbols-outlined text-base">logout</span>
            <span>Sign Out</span>
          </button>
        </div>
      )}

      {/* Account Footer */}
      <div className="mt-auto flex items-center justify-between pt-4 border-t border-[#3d3d3d]/50">
        {currentUser ? (
          <div
            onClick={handleUserClick}
            className="flex items-center gap-3 cursor-pointer group w-full p-1.5 rounded-lg hover:bg-[#252b28] transition-colors"
          >
            <div className="w-8 h-8 rounded-full bg-[#10a37f] flex items-center justify-center text-white text-xs font-bold shadow shrink-0">
              {currentUser.full_name
                ? currentUser.full_name.charAt(0).toUpperCase()
                : currentUser.email.charAt(0).toUpperCase()}
            </div>
            <span className="text-sm text-[#dee4df] font-medium truncate flex-1">
              {currentUser.full_name || currentUser.email}
            </span>
            <span className="material-symbols-outlined text-xs text-gray-400">
              {isUserMenuOpen ? 'expand_more' : 'unfold_more'}
            </span>
          </div>
        ) : (
          <div
            onClick={handleUserClick}
            className="flex items-center gap-3 cursor-pointer hover:text-white transition-colors w-full p-1.5 rounded-lg hover:bg-[#252b28]"
          >
            <div className="w-8 h-8 rounded-full bg-[#2a2a2a] flex items-center justify-center text-xs text-gray-300 shrink-0">
              <span className="material-symbols-outlined text-base">person</span>
            </div>
            <span className="text-sm text-[#dee4df] font-medium">Account</span>
          </div>
        )}
      </div>
    </aside>
  );
}
