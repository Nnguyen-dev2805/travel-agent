import React from 'react';

export default function ChatMessage({ message }) {
  const isUser = message.role === 'user';

  return (
    <div className={`py-5 px-4 md:px-6 w-full ${isUser ? '' : 'bg-[#212121]'}`}>
      <div className="max-w-3xl mx-auto flex gap-4 items-start">
        {/* Avatar */}
        <div
          className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
            isUser ? 'bg-[#383838] text-white' : 'bg-[#10a37f] text-white'
          }`}
        >
          {isUser ? (
            'U'
          ) : (
            <span className="material-symbols-outlined text-sm">auto_awesome</span>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 space-y-2 text-sm md:text-base text-gray-100 leading-relaxed whitespace-pre-wrap">
          {message.content}
        </div>
      </div>
    </div>
  );
}
