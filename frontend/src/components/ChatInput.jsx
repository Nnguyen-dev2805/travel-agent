import React, { useState } from 'react';

export default function ChatInput({ onSendMessage, isLoading }) {
  const [input, setInput] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    onSendMessage(input);
    setInput('');
  };

  return (
    <div className="sticky bottom-0 w-full bg-[#212121] pt-2 pb-6 px-4">
      <div className="max-w-3xl mx-auto">
        <form
          onSubmit={handleSubmit}
          className="relative flex items-center bg-[#2f2f2f] border border-[#424242] rounded-full px-4 py-3 shadow-lg focus-within:border-gray-400 transition-colors"
        >
          {/* Plus icon */}
          <button
            type="button"
            className="text-gray-400 hover:text-white p-1 mr-2 transition-colors"
          >
            <span className="material-symbols-outlined text-xl">add</span>
          </button>

          {/* Text Input */}
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isLoading}
            placeholder="Message ChatGPT..."
            className="flex-1 bg-transparent text-white text-sm md:text-base outline-none placeholder-gray-400 disabled:opacity-50"
          />

          {/* Send Button */}
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${
              input.trim() && !isLoading
                ? 'bg-white text-black hover:bg-gray-200 cursor-pointer'
                : 'bg-[#424242] text-gray-500 cursor-not-allowed'
            }`}
          >
            <span className="material-symbols-outlined text-sm font-bold">arrow_upward</span>
          </button>
        </form>

        <p className="text-[11px] text-center text-gray-500 mt-2">
          ChatGPT can make mistakes. Check important info.
        </p>
      </div>
    </div>
  );
}
