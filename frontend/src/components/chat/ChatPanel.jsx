import React, { useState, useRef, useEffect } from 'react';
import ChatMessage from './ChatMessage';
import ChatInput from './ChatInput';
import CitationDrawer from './CitationDrawer';
import { Compass, Sparkles } from 'lucide-react';

export default function ChatPanel({
  messages = [],
  onSendMessage,
  isLoading = false,
  onViewPlanner,
}) {
  const [selectedCitation, setSelectedCitation] = useState(null);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  return (
    <div className="flex-1 flex flex-col h-full bg-surface-base overflow-hidden relative">
      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto px-4 lg:px-6 py-4 space-y-2">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-8 text-stone-400 space-y-3">
            <div className="w-14 h-14 rounded-2xl bg-surface-muted flex items-center justify-center text-terracotta/70 border border-surface-border">
              <Compass className="w-7 h-7" />
            </div>
            <h3 className="font-bold text-base text-stone-700">
              Bắt đầu trò chuyện với Trợ lý AI
            </h3>
            <p className="text-xs text-stone-500 max-w-sm leading-relaxed">
              Bạn có thể hỏi về điểm tham quan, ẩm thực đặc sản, gợi ý khách sạn hoặc yêu cầu lên lịch trình chi tiết cho chuyến đi này!
            </p>
          </div>
        ) : (
          messages.map((msg, index) => (
            <ChatMessage
              key={msg.message_id || index}
              message={msg}
              onCitationClick={(cit) => setSelectedCitation(cit)}
              onViewPlanner={onViewPlanner}
            />
          ))
        )}

        {/* Loading Spinner Indicator */}
        {isLoading && (
          <div className="flex items-center gap-3 py-3 animate-pulse">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-terracotta to-amber text-white flex items-center justify-center text-xs shadow-xs">
              <Sparkles className="w-4 h-4 animate-spin-slow" />
            </div>
            <div className="px-4 py-3 rounded-2xl rounded-tl-xs bg-surface-card border border-surface-border text-xs text-stone-500 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-terracotta animate-bounce" />
              <span className="w-1.5 h-1.5 rounded-full bg-amber animate-bounce [animation-delay:0.2s]" />
              <span className="w-1.5 h-1.5 rounded-full bg-teal animate-bounce [animation-delay:0.4s]" />
              <span className="ml-1">Đang tìm kiếm cẩm nang & tổng hợp câu trả lời...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <ChatInput onSendMessage={onSendMessage} isLoading={isLoading} />

      {/* Slide-over Citation Drawer */}
      <CitationDrawer
        citation={selectedCitation}
        isOpen={Boolean(selectedCitation)}
        onClose={() => setSelectedCitation(null)}
      />
    </div>
  );
}
