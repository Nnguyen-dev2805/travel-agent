import React, { useRef, useEffect } from 'react';
import ChatMessage from './ChatMessage';
import ChatInput from './ChatInput';
import { Compass } from 'lucide-react';

export default function ChatPanel({
  messages = [],
  onSendMessage,
  isLoading = false,
  onAttachClick,
}) {
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  return (
    <main id="chat-main" className="flex-1 flex flex-col h-full bg-pure-white overflow-hidden relative font-sans">
      {messages.length === 0 ? (
        /* Empty State: Centered Hero & Input matching exact ChatGPT Screenshot */
        <div className="flex-1 flex flex-col items-center justify-center px-4 py-8 max-w-[768px] mx-auto w-full animate-fade-in -mt-10">
          <h1 className="text-[30px] sm:text-[34px] font-medium text-graphite-ink tracking-tight mb-8 text-center select-none">
            Where should we begin?
          </h1>

          {/* Centered Input Box */}
          <div className="w-full">
            <ChatInput
              onSendMessage={onSendMessage}
              isLoading={isLoading}
              onAttachClick={onAttachClick}
              placeholder="Ask anything"
            />
          </div>
        </div>
      ) : (
        /* Active Conversation Mode */
        <>
          <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4 pb-28">
            <div className="max-w-[768px] mx-auto w-full min-h-full flex flex-col justify-between">
              <div className="space-y-2 divide-y divide-hairline">
                {messages.map((msg, index) => (
                  <ChatMessage
                    key={msg.message_id || index}
                    message={msg}
                  />
                ))}

                {/* Minimal Loading Indicator */}
                {isLoading && (
                  <div
                    role="status"
                    aria-live="polite"
                    className="flex gap-3.5 py-4 items-center animate-fade-in"
                  >
                    <div className="w-7 h-7 rounded-lg border border-hairline bg-pure-white text-graphite-ink flex items-center justify-center shrink-0">
                      <Compass className="w-4 h-4 stroke-[1.8]" aria-hidden="true" />
                    </div>
                    <div className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-sidebar-mist border border-hairline text-caption text-mid-ash">
                      <span className="w-1.5 h-1.5 rounded-full bg-graphite-ink animate-pulse motion-reduce:animate-none" aria-hidden="true" />
                      <span className="w-1.5 h-1.5 rounded-full bg-mid-ash animate-pulse [animation-delay:150ms] motion-reduce:animate-none" aria-hidden="true" />
                      <span className="w-1.5 h-1.5 rounded-full bg-hollow animate-pulse [animation-delay:300ms] motion-reduce:animate-none" aria-hidden="true" />
                      <span className="ml-1.5 text-mid-ash">
                        Đang tạo câu trả lời…
                      </span>
                    </div>
                  </div>
                )}
              </div>

              <div ref={messagesEndRef} className="h-6 shrink-0" />
            </div>
          </div>

          {/* Bottom Gradient Mask (pure white fade) */}
          <div className="absolute bottom-0 left-0 right-0 h-24 bg-gradient-to-t from-pure-white via-pure-white/90 to-transparent pointer-events-none z-10" />

          {/* Bottom Input Dock */}
          <div className="relative z-20">
            <ChatInput
              onSendMessage={onSendMessage}
              isLoading={isLoading}
              onAttachClick={onAttachClick}
            />
          </div>
        </>
      )}
    </main>
  );
}
