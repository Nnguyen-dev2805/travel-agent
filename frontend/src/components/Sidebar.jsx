import React, { useState } from 'react';

export default function Sidebar({
  onNewChat,
  isOpen,
  currentUser,
  onOpenAuthModal,
  onOpenFactsModal,
  onLogout,
  sessions = [],
  activeSessionId,
  onSelectSession,
  onDeleteSession,
}) {
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const [isRecentsOpen, setIsRecentsOpen] = useState(true);

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
      <div className="mb-6">
        <h1 className="font-bold text-xl text-white leading-tight">VietraAI</h1>
        <p className="text-xs text-[#9e9e9e] mt-0.5">Vietnam Travel Assistant</p>
      </div>

      {/* Main Navigation Links */}
      <ul className="flex flex-col gap-1 mb-4 shrink-0">
        <li>
          <button
            onClick={onNewChat}
            className="flex items-center gap-3 px-3 py-2.5 rounded-xl bg-[#303633] text-white font-medium cursor-pointer active:scale-95 transition-colors duration-200 w-full text-left"
          >
            <span className="material-symbols-outlined text-[20px]">add</span>
            <span className="text-sm">New Chat</span>
          </button>
        </li>
        <li>
          <button
            onClick={() => setIsRecentsOpen(!isRecentsOpen)}
            className="flex items-center gap-3 px-3 py-2 rounded-xl text-[#dee4df] hover:bg-[#252b28] transition-colors duration-200 cursor-pointer active:scale-95 w-full text-left"
          >
            <span className="material-symbols-outlined text-[20px]">history</span>
            <span className="text-sm">History</span>
          </button>
        </li>
        <li>
          <button
            className="flex items-center gap-3 px-3 py-2 rounded-xl text-[#dee4df] hover:bg-[#252b28] transition-colors duration-200 cursor-pointer active:scale-95 w-full text-left"
          >
            <span className="material-symbols-outlined text-[20px]">settings</span>
            <span className="text-sm">Settings</span>
          </button>
        </li>
        <li>
          <button
            className="flex items-center gap-3 px-3 py-2 rounded-xl text-[#dee4df] hover:bg-[#252b28] transition-colors duration-200 cursor-pointer active:scale-95 w-full text-left"
          >
            <span className="material-symbols-outlined text-[20px]">help</span>
            <span className="text-sm">Help</span>
          </button>
        </li>
      </ul>

      {/* Recents Section matching screenshot style */}
      <div className="flex-grow overflow-y-auto custom-scrollbar flex flex-col pt-3 border-t border-[#2e2e2e]/70">
        {/* Recents Header Bar - Always Visible */}
        <div className="flex items-center justify-between px-2 py-1 mb-1 text-[#e3e3e3]">
          <button
            onClick={() => setIsRecentsOpen(!isRecentsOpen)}
            className="flex items-center gap-1 text-sm font-semibold hover:text-white transition-colors cursor-pointer"
          >
            <span>Recents</span>
            <span className="material-symbols-outlined text-base transition-transform duration-200">
              {isRecentsOpen ? 'expand_more' : 'chevron_right'}
            </span>
          </button>
          <div className="flex items-center gap-2 text-[#9e9e9e]">
            <button title="Options" className="hover:text-white transition-colors p-0.5">
              <span className="material-symbols-outlined text-lg">more_horiz</span>
            </button>
            <button
              onClick={onNewChat}
              title="New Session"
              className="hover:text-white transition-colors p-0.5"
            >
              <span className="material-symbols-outlined text-base">edit_square</span>
            </button>
          </div>
        </div>

        {/* Collapsible Session List */}
        {isRecentsOpen && (
          <div className="flex flex-col gap-0.5 pr-1 animate-in fade-in duration-150">
            {!currentUser && (
              <p className="text-xs text-[#737373] px-2 py-2 italic">
                Đăng nhập để xem lịch sử hội thoại
              </p>
            )}

            {currentUser && sessions.length === 0 && (
              <p className="text-xs text-[#737373] px-2 py-2 italic">Chưa có lịch sử trò chuyện</p>
            )}

            {currentUser &&
              sessions.map((sess) => {
                const isActive = sess.id === activeSessionId;
                return (
                  <div
                    key={sess.id}
                    onClick={() => onSelectSession && onSelectSession(sess.id)}
                    className={`group flex items-center justify-between px-3 py-2 rounded-xl cursor-pointer transition-all duration-150 text-sm ${
                      isActive
                        ? 'bg-[#2a2a2a] text-white font-medium shadow-sm'
                        : 'text-[#d1d1d1] hover:bg-[#212121] hover:text-white'
                    }`}
                  >
                    <span className="truncate text-xs tracking-wide pr-2">
                      {sess.title || 'Cuộc trò chuyện mới'}
                    </span>
                    {onDeleteSession && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeleteSession(sess.id);
                        }}
                        title="Xóa phiên chat"
                        className="opacity-0 group-hover:opacity-100 p-0.5 text-gray-400 hover:text-red-400 transition-opacity shrink-0"
                      >
                        <span className="material-symbols-outlined text-[15px]">delete</span>
                      </button>
                    )}
                  </div>
                );
              })}
          </div>
        )}
      </div>

      {/* Popover Account Menu */}
      {isUserMenuOpen && currentUser && (
        <div className="absolute bottom-16 left-3 right-3 bg-[#252b28] border border-[#3d3d3d] rounded-xl shadow-2xl p-1.5 flex flex-col gap-1 z-50 animate-in fade-in slide-in-from-bottom-2 duration-150">
          <button
            onClick={() => {
              setIsUserMenuOpen(false);
              onOpenFactsModal();
            }}
            className="flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-xs font-medium text-[#dee4df] hover:bg-[#303633] transition-colors text-left"
          >
            <span className="material-symbols-outlined text-base">psychology</span>
            <span>Ký ức AI (User Facts)</span>
          </button>
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

