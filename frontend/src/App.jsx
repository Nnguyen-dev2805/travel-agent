import React, { useState } from 'react';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import WelcomeView from './components/WelcomeView';
import ChatMessage from './components/ChatMessage';
import ChatInput from './components/ChatInput';
import { sendChatMessage } from './services/api';

export default function App() {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  const handleNewChat = () => {
    setMessages([]);
  };

  const handleSendMessage = async (userText) => {
    if (!userText.trim()) return;

    const userMessage = { role: 'user', content: userText };
    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    try {
      const data = await sendChatMessage(userText);
      const botMessage = { role: 'assistant', content: data.reply };
      setMessages((prev) => [...prev, botMessage]);
    } catch (error) {
      const errorMessage = {
        role: 'assistant',
        content: `❌ Lỗi: ${error.message}`,
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-screen w-full bg-[#212121] text-white overflow-hidden">
      {/* Sidebar */}
      <Sidebar
        isOpen={isSidebarOpen}
        onToggle={() => setIsSidebarOpen(!isSidebarOpen)}
        onNewChat={handleNewChat}
      />

      {/* Main Content Area */}
      <div className="flex-1 md:ml-[260px] flex flex-col h-full relative overflow-hidden">
        <Header onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />

        {/* Messages or Welcome View */}
        <div className="flex-1 overflow-y-auto custom-scrollbar">
          {messages.length === 0 ? (
            <WelcomeView onSelectCard={handleSendMessage} />
          ) : (
            <div className="pb-10">
              {messages.map((msg, idx) => (
                <ChatMessage key={idx} message={msg} />
              ))}
              {isLoading && (
                <div className="py-5 px-4 md:px-6 w-full bg-[#212121]">
                  <div className="max-w-3xl mx-auto flex gap-4 items-center">
                    <div className="w-8 h-8 rounded-full bg-[#10a37f] flex items-center justify-center text-xs text-white">
                      <span className="material-symbols-outlined text-sm animate-spin">
                        sync
                      </span>
                    </div>
                    <span className="text-sm text-gray-400">ChatGPT đang suy nghĩ...</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Input */}
        <ChatInput onSendMessage={handleSendMessage} isLoading={isLoading} />
      </div>
    </div>
  );
}
