import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function ChatMessage({ message }) {
  const isUser = message.role === 'user';
  const citations = message.citations || [];

  return (
    <div className="w-full max-w-[768px] mx-auto px-4 md:px-0 py-3">
      <div className="flex gap-4 w-full items-start">
        {/* Avatar */}
        <div
          className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold shrink-0 ${
            isUser
              ? 'bg-[#383838] text-white border border-[#424242]'
              : 'bg-[#10a37f] text-white shadow-sm'
          }`}
        >
          {isUser ? (
            'US'
          ) : (
            <span
              className="material-symbols-outlined text-[18px]"
              style={{ fontVariationSettings: "'FILL' 1" }}
            >
              travel_explore
            </span>
          )}
        </div>

        {/* Message Content */}
        <div className="pt-1 flex-1 min-w-0 flex flex-col gap-3">
          {isUser ? (
            <div className="text-base text-white font-normal leading-relaxed">
              {message.content}
            </div>
          ) : (
            <div className="prose prose-invert max-w-none text-gray-200 leading-relaxed prose-p:leading-relaxed prose-pre:bg-[#171717] prose-pre:border prose-pre:border-[#383838] prose-a:text-[#10a37f]">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            </div>
          )}

          {/* Citations List */}
          {!isUser && citations.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-2">
              {citations.map((cite, idx) => (
                <a
                  key={idx}
                  href={cite.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[#2b2b2b] hover:bg-[#383838] border border-[#383838] text-gray-300 hover:text-white text-xs transition-colors truncate max-w-full"
                >
                  <span className="material-symbols-outlined text-[12px] text-[#10a37f]">
                    link
                  </span>
                  <span>
                    [{idx + 1}] {cite.title || cite.url}
                  </span>
                </a>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
