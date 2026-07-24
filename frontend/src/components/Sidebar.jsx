import React from 'react';

export default function Sidebar({ onNewChat, isOpen, onToggle }) {
  return (
    <aside
      className={`w-[260px] h-full fixed left-0 top-0 bg-[#171717] border-r border-[#2f2f2f] flex flex-col p-4 transition-transform duration-300 z-50 ${
        isOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
      }`}
    >
      <div className="flex flex-col h-full">
        {/* Header / New Chat Button */}
        <div className="mb-4">
          <button
            onClick={onNewChat}
            className="w-full flex items-center justify-between p-3 rounded-lg bg-[#212121] hover:bg-[#2f2f2f] transition-colors text-white mb-2 group border border-[#333333]"
          >
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-white">add</span>
              <span className="font-medium text-sm">New Chat</span>
            </div>
            <span className="material-symbols-outlined text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity">
              edit_square
            </span>
          </button>
        </div>

        {/* History Sections */}
        <nav className="flex-1 overflow-y-auto space-y-6 pr-1">
          <div>
            <h3 className="text-xs font-semibold text-gray-400 px-3 mb-2 uppercase tracking-wider">
              Today
            </h3>
            <div className="space-y-1">
              <div
                onClick={onNewChat}
                className="bg-[#2f2f2f] text-white rounded-lg p-3 flex items-center gap-3 cursor-pointer hover:bg-[#383838] transition-colors"
              >
                <span className="material-symbols-outlined text-[18px]">chat_bubble</span>
                <span className="text-sm truncate">Current Session</span>
              </div>
            </div>
          </div>

          <div>
            <h3 className="text-xs font-semibold text-gray-400 px-3 mb-2 uppercase tracking-wider">
              Previous 7 Days
            </h3>
            <div className="space-y-1">
              <div className="text-gray-300 hover:bg-[#2f2f2f] rounded-lg p-3 flex items-center gap-3 cursor-pointer transition-colors">
                <span className="material-symbols-outlined text-[18px]">map</span>
                <span className="text-sm truncate">Vietnam Travel Demo</span>
              </div>
              <div className="text-gray-300 hover:bg-[#2f2f2f] rounded-lg p-3 flex items-center gap-3 cursor-pointer transition-colors">
                <span className="material-symbols-outlined text-[18px]">code</span>
                <span className="text-sm truncate">FastAPI Architecture</span>
              </div>
            </div>
          </div>
        </nav>

        {/* User Profile Footer */}
        <div className="pt-4 border-t border-[#2f2f2f] mt-4 space-y-1">
          <div className="flex items-center gap-3 p-2 text-gray-200 hover:bg-[#2f2f2f] rounded-lg transition-colors cursor-pointer">
            <div className="w-8 h-8 rounded-full bg-[#10a37f] flex items-center justify-center text-xs font-bold text-white">
              TA
            </div>
            <div className="flex flex-col">
              <span className="text-sm font-medium leading-none text-white">Traveler Admin</span>
              <span className="text-xs text-gray-400 mt-1">Pro Plan</span>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
