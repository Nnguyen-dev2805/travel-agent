import React from 'react';

export default function Sidebar({ onNewChat, isOpen, onToggle }) {
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
              Hôm nay
            </h3>
            <div className="space-y-1">
              <div
                onClick={onNewChat}
                className="bg-[#2f2f2f] border border-[#424242] text-white rounded-xl p-3 flex items-center gap-3 cursor-pointer hover:bg-[#383838] transition-colors"
              >
                <span className="material-symbols-outlined text-base text-[#10a37f]">chat_bubble</span>
                <span className="text-sm font-medium truncate">Phiên hỏi đáp hiện tại</span>
              </div>
            </div>
          </div>

          <div>
            <h3 className="text-xs font-semibold text-gray-400 px-3 mb-2 uppercase tracking-wider">
              Lịch sử tìm kiếm
            </h3>
            <div className="space-y-1">
              <div className="text-gray-300 hover:bg-[#2f2f2f] rounded-xl p-2.5 flex items-center gap-3 cursor-pointer transition-colors">
                <span className="material-symbols-outlined text-base text-gray-400">explore</span>
                <span className="text-sm truncate">Cẩm nang Rooftop Bars</span>
              </div>
              <div className="text-gray-300 hover:bg-[#2f2f2f] rounded-xl p-2.5 flex items-center gap-3 cursor-pointer transition-colors">
                <span className="material-symbols-outlined text-base text-gray-400">map</span>
                <span className="text-sm truncate">Lịch trình Hội An 3N2Đ</span>
              </div>
            </div>
          </div>
        </nav>

        {/* User Profile Footer */}
        <div className="pt-4 border-t border-[#2f2f2f] mt-4 space-y-1">
          <div className="flex items-center gap-3 p-2.5 text-gray-200 hover:bg-[#2f2f2f] rounded-xl transition-colors cursor-pointer">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-[#10a37f] to-[#1a7f64] flex items-center justify-center text-xs font-bold text-white shadow-md shadow-[#10a37f]/20">
              VN
            </div>
            <div className="flex flex-col">
              <span className="text-sm font-semibold leading-none text-white">Traveler User</span>
              <span className="text-[11px] text-[#10a37f] mt-1 font-medium">Vietnam RAG Mode</span>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
