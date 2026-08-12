import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Sparkles, ExternalLink } from 'lucide-react';

export default function ChatMessage({ message }) {
  const isUser = message.role === 'user';
  const citations = message.citations || [];

  return (
    <div className="w-full max-w-[768px] mx-auto px-4 md:px-0 py-3">
      <div className="flex gap-4 w-full items-start">
        {/* Avatar */}
        <div
          className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium shrink-0 ${
            isUser
              ? 'bg-[#0d0d0d] text-white'
              : 'bg-[#f9f9f9] text-[#0d0d0d] border border-[#0000001a]'
          }`}
        >
          {isUser ? (
            'U'
          ) : (
            <Sparkles className="w-3.5 h-3.5 text-[#0d0d0d] stroke-[1.75]" />
          )}
        </div>

        {/* Message Content */}
        <div className="pt-0.5 flex-1 min-w-0 flex flex-col gap-3">
          {isUser ? (
            <div className="text-[16px] leading-[1.5] text-[#0d0d0d] font-normal">
              {message.content}
            </div>
          ) : (
            <div className="prose max-w-none text-[#0d0d0d] text-[16px] leading-[1.5] prose-p:leading-[1.5] prose-p:my-2 prose-headings:text-[#0d0d0d] prose-strong:text-[#0d0d0d] prose-pre:bg-[#f9f9f9] prose-pre:border prose-pre:border-[#0000001a] prose-pre:text-[#0d0d0d] prose-a:text-[#0d0d0d] prose-a:underline">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            </div>
          )}

          {/* Citations List (Chip Badge design) */}
          {!isUser && citations.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-2">
              {citations.map((cite, idx) => (
                <a
                  key={idx}
                  href={cite.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-[#f9f9f9] hover:bg-[#0000000d] border border-[#0000001a] text-[#5d5d5d] hover:text-[#0d0d0d] text-xs transition-colors truncate max-w-full rounded-none"
                >
                  <ExternalLink className="w-3 h-3 text-[#5d5d5d] stroke-[1.75]" />
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
