import React from 'react';

export default function Sidebar({
  onNewChat,
  isOpen,
  currentUser,
  onOpenAuthModal,
  onOpenFactsModal,
}) {
  return (
    <aside
      className={`w-[260px] h-full fixed left-0 top-0 bg-[#171717] border-r border-[#2f2f2f] flex flex-col p-4 transition-transform duration-300 z-50 ${
        isOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
      }`}
    >
      <div className="flex flex-col h-full">
        {/* New Chat Button */}
        <div className="mb-4">
          <button
            onClick={onNewChat}
            className="w-full flex items-center justify-between p-3 rounded-xl bg-[#212121] hover:bg-[#2f2f2f] transition-all duration-200 text-white mb-2 group border border-[#383838] hover:border-[#10a37f]"
          >
            <div className="flex items-center gap-2.5">
              <span className="material-symbols-outlined text-[#10a37f]">add</span>
              <span className="font-semibold text-sm">Cuộc trò chuyện mới</span>
            </div>
            <span className="material-symbols-outlined text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity text-sm">
              edit_square
            </span>
          </button>
        </div>

        {/* History Sections */}
        <nav className="flex-1 overflow-y-auto space-y-6 pr-1 custom-scrollbar">
          <div>
            <h3 className="text-xs font-semibold text-gray-400 px-3 mb-2 uppercase tracking-wider">
              Phiên trò chuyện hiện tại
            </h3>
            <div className="space-y-1">
              <div
                onClick={onNewChat}
                className="bg-[#2f2f2f] border border-[#424242] text-white rounded-xl p-3 flex items-center gap-3 cursor-pointer hover:bg-[#383838] transition-colors"
              >
                <span className="material-symbols-outlined text-base text-[#10a37f]">chat_bubble</span>
                <span className="text-sm font-medium truncate">Cẩm nang Du lịch Việt Nam</span>
              </div>
            </div>
          </div>

          {/* Quick Memory Manager Button for Logged-in User */}
          {currentUser && (
            <div>
              <h3 className="text-xs font-semibold text-gray-400 px-3 mb-2 uppercase tracking-wider">
                Bộ nhớ Cá nhân
              </h3>
              <button
                onClick={onOpenFactsModal}
                className="w-full text-left text-purple-300 hover:bg-purple-500/10 border border-purple-500/30 rounded-xl p-2.5 flex items-center gap-3 transition-colors"
              >
                <span className="material-symbols-outlined text-base text-purple-400">psychology</span>
                <span className="text-xs font-semibold truncate">Xem Ký ức Dài hạn</span>
              </button>
            </div>
          )}
        </nav>

        {/* User Profile Footer */}
        <div className="pt-4 border-t border-[#2f2f2f] mt-4 space-y-1">
          {currentUser ? (
            <div
              onClick={onOpenFactsModal}
              className="flex items-center gap-3 p-2.5 text-gray-200 hover:bg-[#2f2f2f] rounded-xl transition-colors cursor-pointer group"
            >
              <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-purple-600 to-indigo-600 flex items-center justify-center text-xs font-bold text-white shadow-md">
                {currentUser.full_name
                  ? currentUser.full_name.charAt(0).toUpperCase()
                  : currentUser.email.charAt(0).toUpperCase()}
              </div>
              <div className="flex flex-col truncate">
                <span className="text-sm font-semibold leading-none text-white truncate">
                  {currentUser.full_name || currentUser.email}
                </span>
                <span className="text-[11px] text-purple-400 mt-1 font-medium flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-purple-400"></span>
                  Long-term Memory
                </span>
              </div>
            </div>
          ) : (
            <div
              onClick={onOpenAuthModal}
              className="flex items-center gap-3 p-2.5 text-gray-400 hover:bg-[#2f2f2f] hover:text-white rounded-xl transition-colors cursor-pointer"
            >
              <div className="w-9 h-9 rounded-xl bg-[#2a2a2a] flex items-center justify-center text-xs font-bold text-gray-300">
                <span className="material-symbols-outlined text-base">person</span>
              </div>
              <div className="flex flex-col">
                <span className="text-sm font-semibold leading-none text-gray-200">Chế độ Khách (Guest)</span>
                <span className="text-[11px] text-[#10a37f] mt-1 font-medium">Bấm để đăng nhập</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
