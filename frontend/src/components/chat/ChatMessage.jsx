import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { User, Compass, BookOpen, Copy, Check, ThumbsUp } from 'lucide-react';
import CitationPopover from './CitationPopover';

export default function ChatMessage({ message }) {
  const isUser = message.role === 'user';
  const citations = message.citations || [];
  const [copied, setCopied] = useState(false);
  const [liked, setLiked] = useState(false);

  const handleCopy = () => {
    if (!message.content) return;
    if (navigator.clipboard?.writeText) {
      navigator.clipboard
        .writeText(message.content)
        .then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        })
        .catch((err) => {
          console.warn('Không thể sao chép vào clipboard:', err);
        });
    }
  };

  return (
    <div className={`flex gap-3.5 py-4 ${isUser ? 'justify-end' : 'justify-start'} font-sans`}>
      {/* Bot Icon */}
      {!isUser && (
        <div className="w-7 h-7 rounded-lg border border-hairline bg-pure-white text-graphite-ink flex items-center justify-center shrink-0 mt-0.5">
          <Compass className="w-4 h-4 stroke-[1.8]" aria-hidden="true" />
        </div>
      )}

      <div className={`max-w-[88%] sm:max-w-[82%] space-y-1 ${isUser ? 'items-end' : 'items-start'}`}>
        {/* User Message Bubble: Sidebar Mist #f9f9f9, hairline border, 10px radius */}
        {isUser ? (
          <div className="ml-auto text-right">
            <div className="bg-sidebar-mist text-graphite-ink px-4 py-2.5 rounded-lg border border-hairline text-left inline-block text-body leading-body">
              <p className="whitespace-pre-wrap">{message.content}</p>
            </div>
          </div>
        ) : (
          /* Assistant Message Surface: Pure White, Flat by conviction, Graphite Ink typography */
          <div className="space-y-3">
            {/* Markdown Body */}
            <div className="markdown-body font-sans text-graphite-ink text-body leading-body">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  p: ({ children }) => (
                    <p className="mb-3.5 last:mb-0 leading-body text-graphite-ink text-body">
                      {children}
                    </p>
                  ),
                  h1: ({ children }) => (
                    <h1 className="text-heading font-semibold text-graphite-ink mt-6 mb-2 tracking-tight text-balance">
                      {children}
                    </h1>
                  ),
                  h2: ({ children }) => (
                    <h2 className="text-[20px] font-semibold text-graphite-ink mt-5 mb-2 tracking-tight text-balance">
                      {children}
                    </h2>
                  ),
                  h3: ({ children }) => (
                    <h3 className="text-body font-semibold text-graphite-ink mt-4 mb-1.5 tracking-tight text-pretty">
                      {children}
                    </h3>
                  ),
                  ul: ({ children }) => (
                    <ul className="list-disc pl-5 mb-3.5 space-y-1 text-body text-graphite-ink marker:text-mid-ash">
                      {children}
                    </ul>
                  ),
                  ol: ({ children }) => (
                    <ol className="list-decimal pl-5 mb-3.5 space-y-1 text-body text-graphite-ink marker:text-mid-ash font-medium">
                      {children}
                    </ol>
                  ),
                  li: ({ children }) => (
                    <li className="leading-body pl-1 text-graphite-ink font-normal">
                      {children}
                    </li>
                  ),
                  strong: ({ children }) => (
                    <strong className="font-semibold text-graphite-ink">
                      {children}
                    </strong>
                  ),
                  blockquote: ({ children }) => (
                    <blockquote className="my-3 border-l-2 border-graphite-ink bg-sidebar-mist px-3.5 py-2.5 text-mid-ash text-caption rounded-r-lg italic">
                      {children}
                    </blockquote>
                  ),
                  a: ({ href, children }) => (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-graphite-ink underline hover:text-black font-medium transition-colors"
                    >
                      {children}
                    </a>
                  ),
                  table: ({ children }) => (
                    <div className="overflow-x-auto my-3.5 border border-hairline rounded-lg">
                      <table className="min-w-full text-caption text-left tabular-nums">
                        {children}
                      </table>
                    </div>
                  ),
                  thead: ({ children }) => (
                    <thead className="bg-sidebar-mist border-b border-hairline text-graphite-ink font-medium">
                      {children}
                    </thead>
                  ),
                  th: ({ children }) => (
                    <th className="px-3.5 py-2 font-medium text-graphite-ink">
                      {children}
                    </th>
                  ),
                  td: ({ children }) => (
                    <td className="px-3.5 py-2 border-b border-hairline text-graphite-ink last:border-b-0">
                      {children}
                    </td>
                  ),
                  code: ({ inline, children }) =>
                    inline ? (
                      <code className="bg-sidebar-mist text-graphite-ink px-1.5 py-0.5 rounded text-[13px] font-mono border border-hairline">
                        {children}
                      </code>
                    ) : (
                      <pre className="bg-graphite-ink text-pure-white p-3 rounded-lg overflow-x-auto text-[13px] font-mono my-2.5">
                        <code>{children}</code>
                      </pre>
                    ),
                }}
              >
                {message.content}
              </ReactMarkdown>
            </div>

            {/* Citations Shelf */}
            {citations.length > 0 && (
              <div className="pt-2 flex items-center flex-wrap gap-1.5 text-caption text-mid-ash">
                <span className="inline-flex items-center gap-1 text-[12px] font-medium text-mid-ash mr-1 select-none">
                  <BookOpen className="w-3.5 h-3.5" aria-hidden="true" />
                  <span>Nguồn:</span>
                </span>
                {citations.map((cit, idx) => (
                  <CitationPopover key={idx} citation={cit} index={idx} />
                ))}
              </div>
            )}

            {/* Action Bar: Copy & Feedback with Hover Veil */}
            <div className="flex items-center gap-1 pt-1">
              <button
                type="button"
                onClick={handleCopy}
                aria-label="Sao chép nội dung tin nhắn"
                className="flex items-center gap-1 px-2 py-1 rounded-lg text-caption text-mid-ash hover:text-graphite-ink hover:bg-hover-veil transition-colors focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none"
                title="Sao chép"
              >
                {copied ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-graphite-ink" aria-hidden="true" />
                    <span className="text-[12px] font-medium">Đã chép</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" aria-hidden="true" />
                    <span className="text-[12px]">Sao chép</span>
                  </>
                )}
              </button>

              <button
                type="button"
                onClick={() => setLiked(!liked)}
                aria-label={liked ? 'Bỏ đánh giá hữu ích' : 'Đánh giá hữu ích'}
                className={`p-1 rounded-lg transition-colors focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none ${
                  liked
                    ? 'text-graphite-ink bg-hover-veil'
                    : 'text-mid-ash hover:text-graphite-ink hover:bg-hover-veil'
                }`}
                title={liked ? 'Đã thích' : 'Hữu ích'}
              >
                <ThumbsUp className="w-3.5 h-3.5" aria-hidden="true" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* User Avatar */}
      {isUser && (
        <div className="w-7 h-7 rounded-lg border border-hairline bg-sidebar-mist text-graphite-ink flex items-center justify-center shrink-0 mt-0.5 text-caption">
          <User className="w-3.5 h-3.5" aria-hidden="true" />
        </div>
      )}
    </div>
  );
}
