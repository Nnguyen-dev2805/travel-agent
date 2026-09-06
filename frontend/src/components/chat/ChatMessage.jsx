import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { User, Sparkles, BookOpen, Calendar, ArrowUpRight } from 'lucide-react';

export default function ChatMessage({
  message,
  onCitationClick,
  onViewPlanner,
}) {
  const isUser = message.role === 'user';
  const citations = message.citations || [];

  // Check if assistant reply likely generated or updated an itinerary
  const hasItineraryProposal =
    !isUser &&
    message.content &&
    (message.content.toLowerCase().includes('ngày 1') ||
      message.content.toLowerCase().includes('lịch trình') ||
      message.content.toLowerCase().includes('kế hoạch chi tiết'));

  return (
    <div className={`flex gap-3.5 py-4 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {/* Bot Avatar */}
      {!isUser && (
        <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-terracotta to-amber text-white flex items-center justify-center shrink-0 shadow-xs mt-1">
          <Sparkles className="w-4 h-4" />
        </div>
      )}

      <div className={`max-w-[85%] lg:max-w-[78%] space-y-2.5 ${isUser ? 'items-end' : 'items-start'}`}>
        {/* Message Bubble */}
        <div
          className={`p-4 rounded-2xl text-sm leading-relaxed ${
            isUser
              ? 'bg-terracotta text-white rounded-tr-xs shadow-sm font-medium'
              : 'bg-surface-card text-stone-800 border border-surface-border rounded-tl-xs shadow-xs prose prose-stone max-w-none'
          }`}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : (
            <div className="markdown-content">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            </div>
          )}
        </div>

        {/* Action Card: Highlight Itinerary Update if relevant */}
        {hasItineraryProposal && (
          <div className="p-3.5 rounded-xl bg-amber-50/80 border border-amber-200/80 text-xs text-amber-900 flex items-center justify-between shadow-xs animate-fade-in">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-amber-200/60 flex items-center justify-center text-amber-800">
                <Calendar className="w-4 h-4" />
              </div>
              <div>
                <span className="font-bold">Lịch trình đã sẵn sàng!</span>
                <p className="text-[11px] text-amber-800/80">
                  Xem và phê duyệt các chặng trên bảng kế hoạch bên cạnh.
                </p>
              </div>
            </div>
            {onViewPlanner && (
              <button
                type="button"
                onClick={onViewPlanner}
                className="px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white font-semibold text-xs transition-colors flex items-center gap-1 shadow-xs shrink-0"
              >
                <span>Xem lịch trình</span>
                <ArrowUpRight className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        )}

        {/* Citations Badges */}
        {!isUser && citations.length > 0 && (
          <div className="space-y-1 pt-1">
            <div className="text-[11px] font-semibold text-stone-400 uppercase tracking-wider flex items-center gap-1">
              <BookOpen className="w-3 h-3 text-terracotta" />
              <span>Nguồn tham khảo:</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {citations.map((cit, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => onCitationClick && onCitationClick(cit)}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium bg-surface-muted hover:bg-terracotta/10 text-stone-700 hover:text-terracotta border border-surface-border transition-all text-left group"
                >
                  <span className="text-[10px] font-bold text-terracotta">#{idx + 1}</span>
                  <span className="truncate max-w-[200px]">{cit.title || 'Cẩm nang du lịch'}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* User Avatar */}
      {isUser && (
        <div className="w-8 h-8 rounded-xl bg-stone-200 text-stone-700 flex items-center justify-center shrink-0 mt-1 font-semibold text-xs">
          <User className="w-4 h-4" />
        </div>
      )}
    </div>
  );
}
