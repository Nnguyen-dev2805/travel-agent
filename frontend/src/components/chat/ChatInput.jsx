import React, { useState, useRef, useEffect } from 'react';
import { Send, Loader2 } from 'lucide-react';

const SUGGESTION_CHIPS = [
  '🍜 Gợi ý đặc sản địa phương',
  '💰 Dự toán chi phí chi tiết',
  '🛵 Phương tiện di chuyển tốt nhất',
  '🏨 Chỗ nghỉ view đẹp, giá hợp lý',
];

export default function ChatInput({ onSendMessage, isLoading = false, disabled = false }) {
  const [text, setText] = useState('');
  const textareaRef = useRef(null);

  // Auto-grow textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(
        textareaRef.current.scrollHeight,
        140
      )}px`;
    }
  }, [text]);

  const handleSubmit = (e) => {
    e?.preventDefault();
    if (!text.trim() || isLoading || disabled) return;
    onSendMessage(text);
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

  const handleChipClick = (chip) => {
    if (isLoading || disabled) return;
    onSendMessage(chip);
  };

  return (
    <div className="p-4 bg-surface-card border-t border-surface-border space-y-2.5">
      {/* Quick Suggestion Chips */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 no-scrollbar">
        {SUGGESTION_CHIPS.map((chip, idx) => (
          <button
            key={idx}
            type="button"
            disabled={isLoading || disabled}
            onClick={() => handleChipClick(chip)}
            className="px-2.5 py-1 rounded-full text-xs bg-surface-muted hover:bg-terracotta/10 text-stone-600 hover:text-terracotta border border-surface-border whitespace-nowrap transition-colors disabled:opacity-50"
          >
            {chip}
          </button>
        ))}
      </div>

      {/* Textarea Input Container */}
      <form onSubmit={handleSubmit} className="relative flex items-end gap-2 bg-surface-base rounded-2xl border border-surface-border p-2 focus-within:ring-2 focus-within:ring-terracotta/30 focus-within:border-terracotta transition-all shadow-xs">
        <textarea
          ref={textareaRef}
          rows={1}
          value={text}
          disabled={disabled || isLoading}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Hỏi trợ lý về địa điểm, lịch trình, ẩm thực... (Enter để gửi)"
          className="flex-1 bg-transparent border-none text-sm text-stone-800 placeholder-stone-400 focus:outline-none resize-none py-1.5 px-2 max-h-36"
        />

        <button
          type="submit"
          disabled={!text.trim() || isLoading || disabled}
          className="w-9 h-9 rounded-xl bg-terracotta hover:bg-terracotta-hover text-white flex items-center justify-center disabled:opacity-40 disabled:hover:bg-terracotta transition-all shadow-xs shrink-0"
        >
          {isLoading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Send className="w-4 h-4" />
          )}
        </button>
      </form>
    </div>
  );
}
