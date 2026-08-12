import React, { useState } from 'react';
import {
  Sparkles,
  PanelLeft,
  SquarePen,
  Search,
  Image,
  LayoutGrid,
  Pin,
  MessageSquare,
  Settings,
  HelpCircle,
  Brain,
  LogOut,
  Trash2,
  ChevronDown,
  ChevronRight,
  ChevronsUpDown,
  User,
} from 'lucide-react';

export default function Sidebar({
  onNewChat,
  isOpen,
  onToggle,
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

  // Dynamic User Initials Extractor
  const getInitials = (user) => {
    if (!user) return '';
    if (user.full_name && user.full_name.trim()) {
      const parts = user.full_name.trim().split(' ');
      if (parts.length >= 2) {
        return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
      }
      return parts[0].slice(0, 2).toUpperCase();
    }
    return (user.email || 'U').slice(0, 2).toUpperCase();
  };

  // -----------------------------------------------------------
  // 1. COLLAPSED MINI RAIL MODE (Width: 56px)
  // -----------------------------------------------------------
  if (!isOpen) {
    return (
      <aside className="fixed left-0 top-0 h-full w-[56px] bg-[#f9f9f9] text-[#0d0d0d] flex flex-col items-center justify-between py-3 px-2 z-40 border-r border-[#0000001a] transition-all duration-300">
        {/* Top Section: App Logo (Click to expand) */}
        <div className="flex flex-col items-center gap-4">
          <button
            onClick={onToggle}
            title="Open sidebar"
            className="group relative p-2 rounded-xl text-[#0d0d0d] hover:bg-[#0000000d] transition-colors cursor-pointer"
          >
            {/* Default Logo Icon */}
            <Sparkles className="w-5 h-5 block group-hover:hidden stroke-[1.75]" />
            {/* Hover Open Sidebar Icon */}
            <PanelLeft className="w-5 h-5 hidden group-hover:block stroke-[1.75]" />
          </button>

          {/* Vertical Icon Actions Stack */}
          <div className="flex flex-col gap-2.5 items-center mt-1">
            <button
              onClick={onNewChat}
              title="New chat"
              className="p-2 rounded-xl text-[#0d0d0d] hover:bg-[#0000000d] transition-colors cursor-pointer"
            >
              <SquarePen className="w-[18px] h-[18px] stroke-[1.75]" />
            </button>

            <button
              onClick={onToggle}
              title="Search chats"
              className="p-2 rounded-xl text-[#5d5d5d] hover:text-[#0d0d0d] hover:bg-[#0000000d] transition-colors cursor-pointer"
            >
              <Search className="w-[18px] h-[18px] stroke-[1.75]" />
            </button>

            <button
              onClick={onToggle}
              title="Pinned chats"
              className="p-2 rounded-xl text-[#5d5d5d] hover:text-[#0d0d0d] hover:bg-[#0000000d] transition-colors cursor-pointer"
            >
              <Pin className="w-[18px] h-[18px] stroke-[1.75]" />
            </button>

            <button
              onClick={onToggle}
              title="Recent chats"
              className="p-2 rounded-xl text-[#5d5d5d] hover:text-[#0d0d0d] hover:bg-[#0000000d] transition-colors cursor-pointer"
            >
              <MessageSquare className="w-[18px] h-[18px] stroke-[1.75]" />
            </button>
          </div>
        </div>

        {/* Bottom Section: User Avatar or Log In Icon */}
        <div className="flex flex-col items-center pb-1">
          {currentUser ? (
            <button
              onClick={handleUserClick}
              title={currentUser.full_name || currentUser.email}
              className="w-8 h-8 rounded-full bg-[#8b5cf6] text-white flex items-center justify-center text-xs font-semibold shadow-sm hover:opacity-90 transition-opacity cursor-pointer"
            >
              {getInitials(currentUser)}
            </button>
          ) : (
            <button
              onClick={handleUserClick}
              title="Log in"
              className="w-8 h-8 rounded-full bg-[#ffffff] text-[#0d0d0d] border border-[#0000001a] hover:bg-[#0000000d] flex items-center justify-center transition-colors cursor-pointer"
            >
              <User className="w-4 h-4 stroke-[1.75]" />
            </button>
          )}
        </div>
      </aside>
    );
  }

  // -----------------------------------------------------------
  // 2. EXPANDED SIDEBAR MODE (Width: 260px)
  // -----------------------------------------------------------
  return (
    <aside className="fixed left-0 top-0 h-full w-[260px] bg-[#f9f9f9] text-[#0d0d0d] flex flex-col p-3 z-50 border-r border-[#0000001a] shadow-xl transition-all duration-300">
      {/* Sidebar Header Bar (Logo + Sidebar Collapse Button) */}
      <div className="flex items-center justify-between px-2 py-2 mb-3">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-[#0d0d0d] stroke-[1.75]" />
          <span className="font-semibold text-base text-[#0d0d0d] tracking-tight">VietraAI</span>
        </div>
        <button
          onClick={onToggle}
          title="Close sidebar"
          className="p-1.5 text-[#5d5d5d] hover:text-[#0d0d0d] hover:bg-[#0000000d] rounded-lg transition-colors cursor-pointer"
        >
          <PanelLeft className="w-5 h-5 stroke-[1.75]" />
        </button>
      </div>

      {/* Primary Navigation Links */}
      <ul className="flex flex-col gap-0.5 mb-2 shrink-0">
        <li>
          <button
            onClick={onNewChat}
            className="flex items-center gap-3 px-3 py-2 rounded-[10px] text-[#0d0d0d] hover:bg-[#0000000d] font-normal cursor-pointer transition-colors duration-150 w-full text-left"
          >
            <SquarePen className="w-[18px] h-[18px] text-[#0d0d0d] stroke-[1.75]" />
            <span className="text-sm">New chat</span>
          </button>
        </li>
        <li>
          <button
            className="flex items-center gap-3 px-3 py-2 rounded-[10px] text-[#0d0d0d] hover:bg-[#0000000d] transition-colors duration-150 cursor-pointer w-full text-left"
          >
            <Search className="w-[18px] h-[18px] text-[#0d0d0d] stroke-[1.75]" />
            <span className="text-sm">Search chats</span>
          </button>
        </li>
        <li>
          <button
            className="flex items-center gap-3 px-3 py-2 rounded-[10px] text-[#0d0d0d] hover:bg-[#0000000d] transition-colors duration-150 cursor-pointer w-full text-left"
          >
            <Image className="w-[18px] h-[18px] text-[#0d0d0d] stroke-[1.75]" />
            <span className="text-sm">Images</span>
          </button>
        </li>
        <li>
          <button
            className="flex items-center gap-3 px-3 py-2 rounded-[10px] text-[#0d0d0d] hover:bg-[#0000000d] transition-colors duration-150 cursor-pointer w-full text-left"
          >
            <LayoutGrid className="w-[18px] h-[18px] text-[#0d0d0d] stroke-[1.75]" />
            <span className="text-sm">Apps</span>
          </button>
        </li>
      </ul>

      {/* Recents Session History Container */}
      <div className="flex-grow overflow-y-auto custom-scrollbar flex flex-col py-1">
        {currentUser && (
          <div className="flex items-center justify-between px-2 py-1 mb-1 text-[#5d5d5d]">
            <button
              onClick={() => setIsRecentsOpen(!isRecentsOpen)}
              className="flex items-center gap-1 text-xs font-semibold text-[#5d5d5d] hover:text-[#0d0d0d] transition-colors cursor-pointer"
            >
              <span>Recents</span>
              {isRecentsOpen ? (
                <ChevronDown className="w-4 h-4 stroke-[1.75]" />
              ) : (
                <ChevronRight className="w-4 h-4 stroke-[1.75]" />
              )}
            </button>
          </div>
        )}

        {/* Collapsible Session List */}
        {currentUser && isRecentsOpen && (
          <div className="flex flex-col gap-[2px] animate-in fade-in duration-150">
            {sessions.length === 0 ? (
              <p className="text-xs text-[#8f8f8f] px-2 py-1.5 italic">No chat history yet</p>
            ) : (
              sessions.map((sess) => {
                const isActive = sess.id === activeSessionId;
                return (
                  <div
                    key={sess.id}
                    onClick={() => onSelectSession && onSelectSession(sess.id)}
                    className={`group flex items-center justify-between px-3 py-1.5 rounded-[10px] cursor-pointer transition-colors duration-150 text-sm ${
                      isActive
                        ? 'bg-[#0000000d] text-[#0d0d0d] font-medium'
                        : 'text-[#5d5d5d] hover:bg-[#0000000d] hover:text-[#0d0d0d]'
                    }`}
                  >
                    <span className="truncate text-xs tracking-normal pr-2">
                      {sess.title || 'New Chat'}
                    </span>
                    {onDeleteSession && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeleteSession(sess.id);
                        }}
                        title="Delete chat"
                        className="opacity-0 group-hover:opacity-100 p-0.5 text-[#8f8f8f] hover:text-[#0d0d0d] transition-opacity shrink-0"
                      >
                        <Trash2 className="w-3.5 h-3.5 stroke-[1.75]" />
                      </button>
                    )}
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>

      {/* Popover Account Menu */}
      {isUserMenuOpen && currentUser && (
        <div className="absolute bottom-16 left-3 right-3 bg-[#ffffff] border border-[#0000001a] rounded-[10px] p-1.5 flex flex-col gap-0.5 z-50 shadow-[0_4px_16px_rgba(0,0,0,0.08)] animate-in fade-in slide-in-from-bottom-2 duration-150">
          <button
            onClick={() => {
              setIsUserMenuOpen(false);
              onOpenFactsModal();
            }}
            className="flex items-center gap-3 w-full px-3 py-2 rounded-[10px] text-sm font-normal text-[#0d0d0d] hover:bg-[#0000000d] transition-colors text-left cursor-pointer"
          >
            <Brain className="w-[18px] h-[18px] text-[#0d0d0d] stroke-[1.75]" />
            <span>AI Memory (User Facts)</span>
          </button>

          <button
            onClick={() => setIsUserMenuOpen(false)}
            className="flex items-center gap-3 w-full px-3 py-2 rounded-[10px] text-sm font-normal text-[#0d0d0d] hover:bg-[#0000000d] transition-colors text-left cursor-pointer"
          >
            <Settings className="w-[18px] h-[18px] text-[#0d0d0d] stroke-[1.75]" />
            <span>Settings</span>
          </button>

          <button
            onClick={() => setIsUserMenuOpen(false)}
            className="flex items-center gap-3 w-full px-3 py-2 rounded-[10px] text-sm font-normal text-[#0d0d0d] hover:bg-[#0000000d] transition-colors text-left cursor-pointer"
          >
            <HelpCircle className="w-[18px] h-[18px] text-[#0d0d0d] stroke-[1.75]" />
            <span>Help</span>
          </button>

          <div className="border-t border-[#0000001a] my-1" />

          <button
            onClick={() => {
              setIsUserMenuOpen(false);
              onLogout();
            }}
            className="flex items-center gap-3 w-full px-3 py-2 rounded-[10px] text-sm font-normal text-[#0d0d0d] hover:bg-[#0000000d] transition-colors text-left cursor-pointer"
          >
            <LogOut className="w-[18px] h-[18px] text-[#0d0d0d] stroke-[1.75]" />
            <span>Sign Out</span>
          </button>
        </div>
      )}

      {/* Sidebar Tail / Footer Block */}
      <div className="mt-auto pt-2 border-t border-[#0000001a] flex flex-col gap-1 shrink-0">
        {/* Tail block when logged out */}
        {!currentUser ? (
          <div className="mt-1 pt-1 flex flex-col gap-1.5 px-1 pb-1">
            <h4 className="text-sm font-semibold text-[#0d0d0d] leading-snug">
              Get responses tailored to you
            </h4>
            <p className="text-xs text-[#8f8f8f] leading-relaxed">
              Log in to get answers based on saved chats, plus create images and upload files.
            </p>
            <button
              onClick={handleUserClick}
              className="mt-2 w-full flex items-center justify-center bg-[#ffffff] text-[#0d0d0d] border border-[#0000001a] rounded-full py-2.5 px-4 text-sm font-medium hover:bg-[#0000000d] transition-colors cursor-pointer"
            >
              Log in
            </button>
          </div>
        ) : (
          <div
            onClick={handleUserClick}
            className="flex items-center gap-3 cursor-pointer group w-full p-2 rounded-[10px] hover:bg-[#0000000d] transition-colors"
          >
            <div className="w-7 h-7 rounded-full bg-[#8b5cf6] flex items-center justify-center text-white text-xs font-semibold shrink-0">
              {getInitials(currentUser)}
            </div>
            <span className="text-sm text-[#0d0d0d] font-medium truncate flex-1">
              {currentUser.full_name || currentUser.email}
            </span>
            <ChevronsUpDown className="w-4 h-4 text-[#8f8f8f] stroke-[1.75]" />
          </div>
        )}
      </div>
    </aside>
  );
}

