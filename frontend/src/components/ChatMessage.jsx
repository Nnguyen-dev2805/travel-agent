import React from 'react';

export default function ChatMessage({ message }) {
  const isUser = message.role === 'user';
  const citations = message.citations || [];

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

        {/* Content & Citations */}
        <div className="flex-1 space-y-3 text-sm md:text-base text-gray-100 leading-relaxed whitespace-pre-wrap">
          <div>{message.content}</div>

          {/* Citations List */}
          {!isUser && citations.length > 0 && (
            <div className="mt-4 pt-3 border-t border-[#383838]">
              <div className="text-xs font-semibold text-gray-400 mb-2 flex items-center gap-1.5">
                <span className="material-symbols-outlined text-sm text-[#10a37f]">link</span>
                Nguồn tham khảo (Citations):
              </div>
              <div className="flex flex-wrap gap-2">
                {citations.map((cite, idx) => (
                  <a
                    key={idx}
                    href={cite.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#2f2f2f] hover:bg-[#383838] border border-[#424242] text-xs text-[#10a37f] hover:text-white transition-colors max-w-full truncate"
                  >
                    <span className="material-symbols-outlined text-xs">open_in_new</span>
                    <span className="truncate">{cite.title || cite.url}</span>
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
