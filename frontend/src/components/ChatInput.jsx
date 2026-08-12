import React, { useState } from 'react';
import { Plus, ArrowUp, AudioLines } from 'lucide-react';

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
    <div className="w-full max-w-[768px] mx-auto px-4 md:px-6 pb-6 pt-2 bg-gradient-to-t from-[#ffffff] via-[#ffffff] to-transparent sticky bottom-0 z-30">
      <form onSubmit={handleSubmit} className="relative w-full">
        <div className="relative flex items-center w-full bg-[#ffffff] border border-[#0000001a] hover:border-[#00000033] focus-within:border-[#0d0d0d] focus-within:ring-1 focus-within:ring-[#0d0d0d] rounded-full shadow-[0_2px_10px_rgba(0,0,0,0.02)] transition-all duration-200">
          {/* Left Plus Icon */}
          <button
            type="button"
            title="Add attachment or tool"
            className="pl-4 pr-2 text-[#5d5d5d] hover:text-[#0d0d0d] flex items-center justify-center transition-colors cursor-pointer"
          >
            <Plus className="w-5 h-5 stroke-[1.75]" />
          </button>

          {/* Main Text Input */}
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            placeholder="Ask anything"
            className="w-full bg-transparent text-[#0d0d0d] text-base py-3.5 pr-24 outline-none placeholder:text-[#8f8f8f]"
          />

          {/* Right Action Button */}
          <div className="absolute right-2.5 flex items-center gap-1.5">
            {input.trim() && !isLoading ? (
              <button
                type="submit"
                className="w-8 h-8 rounded-full bg-[#0d0d0d] text-white hover:bg-[#000000] flex items-center justify-center transition-colors cursor-pointer"
              >
                <ArrowUp className="w-4 h-4 stroke-[2]" />
              </button>
            ) : (
              <button
                type="button"
                title="Voice input"
                className="flex items-center gap-1.5 px-3 py-1 bg-[#0000000d] hover:bg-[#0000001a] text-[#0d0d0d] text-xs font-medium rounded-full transition-colors cursor-pointer"
              >
                <AudioLines className="w-4 h-4 stroke-[1.75]" />
                <span>Voice</span>
              </button>
            )}
          </div>
        </div>
      </form>
      <p className="text-center text-xs text-[#8f8f8f] leading-normal mt-2.5 px-2 md:whitespace-nowrap">
        By messaging VietraAI, an AI chatbot, you agree to our{' '}
        <a href="#" className="underline hover:text-[#0d0d0d] transition-colors">
          Terms
        </a>{' '}
        and have read our{' '}
        <a href="#" className="underline hover:text-[#0d0d0d] transition-colors">
          Privacy Policy
        </a>
        . See{' '}
        <a href="#" className="underline hover:text-[#0d0d0d] transition-colors">
          Cookie Preferences
        </a>
        .
      </p>
    </div>
  );
}
