import React, { useState } from 'react';

export default function ChatInput({ onSendMessage, isLoading }) {
  const [input, setInput] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    onSendMessage(input);
    setInput('');
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="w-full max-w-[768px] mx-auto px-6 pb-8 pt-4 bg-gradient-to-t from-[#212121] via-[#212121] to-transparent sticky bottom-0 z-30">
      <form onSubmit={handleSubmit} className="relative w-full">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isLoading}
          placeholder="Message VietraAI..."
          className="w-full bg-[#2f2f2f] text-white text-base rounded-xl py-4 pl-5 pr-14 outline-none focus:ring-1 focus:ring-[#61dbb4]/50 border-none placeholder:text-[#b4b4b4] shadow-[0_4px_20px_rgba(0,0,0,0.2)]"
        />
        <button
          type="submit"
          disabled={!input.trim() || isLoading}
          className={`absolute right-3 top-1/2 -translate-y-1/2 w-8 h-8 flex items-center justify-center rounded-lg transition-colors ${
            input.trim() && !isLoading
              ? 'bg-[#10a37f] text-white hover:bg-[#12a480] cursor-pointer'
              : 'bg-[#3d3d3d] text-gray-400 cursor-not-allowed'
          }`}
        >
          <span className="material-symbols-outlined text-[18px]">
            arrow_upward
          </span>
        </button>
      </form>
      <p className="text-center text-xs text-[#666666] mt-3">
        VietraAI can make mistakes. Verify important travel information.
      </p>
    </div>
  );
}
