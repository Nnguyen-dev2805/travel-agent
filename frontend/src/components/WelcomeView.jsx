import React, { useState } from 'react';
import { Plus, ArrowUp, AudioLines } from 'lucide-react';

export default function WelcomeView({ currentUser, onSelectCard, onSendMessage }) {
  const [input, setInput] = useState('');

  const getGreetingText = () => {
    if (currentUser) {
      const name = currentUser.full_name ? currentUser.full_name.trim().split(' ')[0] : currentUser.email.split('@')[0];
      return `Hi ${name}, where would you like to explore?`;
    }
    return 'Where would you like to explore?';
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!input.trim() || !onSendMessage) return;
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
    <div className="flex-1 w-full flex flex-col justify-between items-center mx-auto px-4 md:px-6 py-6 min-h-[calc(100vh-64px)]">
      {/* Upper Spacer for vertical alignment */}
      <div className="flex-1"></div>

      {/* Main Centered Content */}
      <div className="w-full flex flex-col items-center max-w-[680px] my-auto">
        {/* Title */}
        <h1 className="text-[32px] md:text-[36px] font-medium text-[#0d0d0d] text-center leading-[1.2] tracking-tight mb-8">
          {getGreetingText()}
        </h1>

        {/* Hero Centered Input Capsule */}
        <form onSubmit={handleSubmit} className="relative w-full">
          <div className="relative flex items-center w-full min-h-[56px] bg-[#ffffff] border border-[#0000001a] hover:border-[#00000033] focus-within:border-[#0d0d0d] focus-within:ring-1 focus-within:ring-[#0d0d0d] rounded-full shadow-[0_2px_12px_rgba(0,0,0,0.04)] transition-all duration-200">
            {/* Left Plus Icon */}
            <button
              type="button"
              title="Add attachment or tool"
              className="absolute left-4 text-[#5d5d5d] hover:text-[#0d0d0d] flex items-center justify-center transition-colors cursor-pointer p-1"
            >
              <Plus className="w-5 h-5 stroke-[1.75]" />
            </button>

            {/* Main Input Text Area */}
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask anything"
              className="w-full bg-transparent text-[#0d0d0d] text-base py-4 pl-12 pr-28 outline-none placeholder:text-[#8f8f8f]"
            />

            {/* Right Action Button: Voice Pill or Send Arrow */}
            <div className="absolute right-3 flex items-center gap-1.5">
              {input.trim() ? (
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
                  className="flex items-center gap-1.5 px-3.5 py-1.5 bg-[#0000000d] hover:bg-[#0000001a] text-[#0d0d0d] text-xs font-medium rounded-full transition-colors cursor-pointer"
                >
                  <AudioLines className="w-4 h-4 stroke-[1.75]" />
                  <span>Voice</span>
                </button>
              )}
            </div>
          </div>
        </form>
      </div>

      {/* Lower Spacer */}
      <div className="flex-1 flex items-end w-full justify-center">
        <p className="text-center text-xs text-[#8f8f8f] leading-relaxed max-w-none md:whitespace-nowrap px-4 pb-2">
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
    </div>
  );
}
