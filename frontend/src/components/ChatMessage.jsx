import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function ChatMessage({ message }) {
  const isUser = message.role === 'user';
  const citations = message.citations || [];

  return (
    <div className={`py-6 px-4 md:px-6 w-full ${isUser ? '' : 'bg-[#212121] border-y border-[#2f2f2f]'}`}>
      <div className="max-w-3xl mx-auto flex gap-4 items-start">
        {/* Avatar */}
        <div
          className={`w-9 h-9 rounded-xl flex items-center justify-center text-xs font-bold shrink-0 shadow-md ${
            isUser ? 'bg-[#383838] text-white border border-[#424242]' : 'bg-[#10a37f] text-white shadow-[#10a37f]/20'
          }`}
        >
          {isUser ? (
            'U'
          ) : (
            <span className="material-symbols-outlined text-base">auto_awesome</span>
          )}
        </div>

        {/* Content & Citations */}
        <div className="flex-1 space-y-3 text-sm md:text-base text-gray-200 leading-relaxed overflow-hidden">
          {isUser ? (
            <div className="font-medium text-white">{message.content}</div>
          ) : (
            <div className="prose prose-invert max-w-none prose-p:leading-relaxed prose-pre:bg-[#171717] prose-pre:border prose-pre:border-[#383838] prose-a:text-[#10a37f]">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            </div>
          )}

          {/* Citations List */}
          {!isUser && citations.length > 0 && (
            <div className="mt-5 pt-4 border-t border-[#383838]">
              <div className="text-xs font-semibold text-gray-400 mb-2.5 flex items-center gap-1.5 uppercase tracking-wider">
                <span className="material-symbols-outlined text-sm text-[#10a37f]">link</span>
                Nguồn tham khảo (Citations):
              </div>
              <div className="flex flex-wrap gap-2.5">
                {citations.map((cite, idx) => (
                  <a
                    key={idx}
                    href={cite.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group inline-flex items-center gap-2 px-3 py-2 rounded-xl bg-[#2f2f2f] hover:bg-[#383838] border border-[#424242] hover:border-[#10a37f] text-xs text-gray-300 hover:text-white transition-all duration-200 hover:scale-[1.02] shadow-sm max-w-full truncate"
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-[#10a37f] group-hover:animate-ping"></span>
                    <span className="truncate max-w-[280px]">{cite.title || cite.url}</span>
                    <span className="material-symbols-outlined text-xs text-gray-400 group-hover:text-[#10a37f] transition-colors">
                      open_in_new
                    </span>
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
