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
    <div className="sticky bottom-0 w-full bg-gradient-to-t from-[#212121] via-[#212121]/95 to-transparent pt-4 pb-6 px-4">
      <div className="max-w-3xl mx-auto">
        <form
          onSubmit={handleSubmit}
          className="relative flex items-center bg-[#2f2f2f] border border-[#424242] focus-within:border-[#10a37f] focus-within:ring-1 focus-within:ring-[#10a37f]/50 rounded-2xl px-4 py-3 shadow-xl transition-all duration-200"
        >
          {/* Plus icon */}
          <button
            type="button"
            className="text-gray-400 hover:text-white p-1 mr-2 transition-colors"
            title="Thêm đính kèm"
          >
            <span className="material-symbols-outlined text-xl">add</span>
          </button>

          {/* Text Input */}
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isLoading}
            placeholder="Hỏi bất kỳ điều gì về địa điểm, khách sạn, ẩm thực Việt Nam..."
            className="flex-1 bg-transparent text-white text-sm md:text-base outline-none placeholder-gray-400 disabled:opacity-50"
          />

          {/* Send Button */}
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-200 ${
              input.trim() && !isLoading
                ? 'bg-[#10a37f] text-white hover:bg-[#1a7f64] cursor-pointer shadow-md shadow-[#10a37f]/20 hover:scale-105'
                : 'bg-[#383838] text-gray-500 cursor-not-allowed'
            }`}
          >
            <span className="material-symbols-outlined text-base font-bold">arrow_upward</span>
          </button>
        </form>

        <p className="text-[11px] text-center text-gray-500 mt-2">
          Vietnam Travel Agent có thể mắc lỗi nhỏ. Hãy kiểm tra lại thông tin quan trọng.
        </p>
      </div>
    </div>
  );
}
