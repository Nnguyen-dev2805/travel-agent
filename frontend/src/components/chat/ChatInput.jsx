import React, { useState, useRef, useEffect } from 'react';
import { ArrowUp, Loader2, Plus } from 'lucide-react';

export default function ChatInput({
  onSendMessage,
  isLoading = false,
  disabled = false,
  onAttachClick,
  placeholder = 'Hỏi bất kỳ điều gì…',
}) {
  const [text, setText] = useState('');
  const textareaRef = useRef(null);

  // Auto-grow textarea smoothly
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(
        textareaRef.current.scrollHeight,
        200
      )}px`;
    }
  }, [text]);

  const handleSubmit = (e) => {
    e?.preventDefault();
    if (!text.trim() || isLoading || disabled) return;
    onSendMessage(text.trim());
    setText('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const hasContent = Boolean(text.trim());

  return (
    <div className="w-full max-w-[768px] mx-auto px-4 pb-3 pt-1 font-sans">
      <form
        onSubmit={handleSubmit}
        className="relative flex items-end gap-2 bg-pure-white rounded-[26px] border border-hairline p-2 pl-3 transition-colors focus-within:border-graphite-ink focus-within:ring-1 focus-within:ring-graphite-ink group"
      >
        {/* Plus / Options Button matching ChatGPT */}
        <button
          type="button"
          onClick={onAttachClick}
          aria-label="Tùy chọn bổ sung"
          title="Tùy chọn"
          className="w-8 h-8 rounded-full flex items-center justify-center text-graphite-ink hover:bg-hover-veil transition-colors shrink-0 mb-0.5 focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none"
        >
          <Plus className="w-4 h-4 stroke-[2]" aria-hidden="true" />
        </button>

        <label htmlFor="chat_message_input" className="sr-only">
          Nội dung câu hỏi
        </label>
        <textarea
          id="chat_message_input"
          name="chat_message"
          autoComplete="off"
          spellCheck="false"
          ref={textareaRef}
          rows={1}
          value={text}
          disabled={disabled || isLoading}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className="flex-1 bg-transparent border-none text-body leading-body text-graphite-ink placeholder-hollow focus:outline-none resize-none py-1.5 px-1 max-h-48 font-sans"
        />

        <div className="flex items-center gap-1.5 shrink-0 mb-0.5 pr-1">
          <button
            type="submit"
            aria-label="Gửi câu hỏi"
            disabled={!hasContent || isLoading || disabled}
            className={`w-8 h-8 rounded-full flex items-center justify-center transition-colors focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none ${
              hasContent && !isLoading
                ? 'bg-graphite-ink hover:bg-ink-press text-pure-white cursor-pointer'
                : 'bg-sidebar-mist text-hollow cursor-not-allowed border border-hairline'
            }`}
            title="Gửi câu hỏi"
          >
            {isLoading ? (
              <Loader2 className="w-4 h-4 animate-spin text-mid-ash motion-reduce:animate-none" aria-hidden="true" />
            ) : (
              <ArrowUp className="w-4 h-4 stroke-[2.2]" aria-hidden="true" />
            )}
          </button>
        </div>
      </form>

      {/* Production Grade Clean Disclaimer */}
      <div className="text-center mt-2.5 text-[12px] text-hollow select-none">
        Travel Agent có thể mắc lỗi. Hãy kiểm tra lại các thông tin du lịch quan trọng.
      </div>
    </div>
  );
}
