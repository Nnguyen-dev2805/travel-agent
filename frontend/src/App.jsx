import React, { useEffect, useState } from 'react';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import WelcomeView from './components/WelcomeView';
import ChatMessage from './components/ChatMessage';
import ChatInput from './components/ChatInput';
import AuthModal from './components/AuthModal';
import UserFactsModal from './components/UserFactsModal';
import {
  sendChatMessage,
  getCurrentUser,
  logoutUser,
  getStoredSessionId,
  createNewSessionId,
} from './services/api';

export default function App() {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  // User Auth & Modal States
  const [currentUser, setCurrentUser] = useState(null);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [isFactsModalOpen, setIsFactsModalOpen] = useState(false);

  // Active Chat Session ID
  const [sessionId, setSessionId] = useState(getStoredSessionId());

  // Check auth user status on app mount
  useEffect(() => {
    async function checkAuth() {
      const user = await getCurrentUser();
      if (user) {
        setCurrentUser(user);
      }
    }
    checkAuth();
  }, []);

  const handleNewChat = () => {
    const newSid = createNewSessionId();
    setSessionId(newSid);
    setMessages([]);
  };

  const handleLogout = () => {
    logoutUser();
    setCurrentUser(null);
  };

  const handleSendMessage = async (userText) => {
    if (!userText.trim()) return;

    const userMessage = { role: 'user', content: userText };
    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    try {
      const data = await sendChatMessage(userText, sessionId);
      const botMessage = {
        role: 'assistant',
        content: data.reply,
        citations: data.citations || [],
      };
      setMessages((prev) => [...prev, botMessage]);

      // If session_id returned from API, sync state
      if (data.session_id && data.session_id !== sessionId) {
        setSessionId(data.session_id);
      }
    } catch (error) {
      const errorMessage = {
        role: 'assistant',
        content: `❌ Lỗi kết nối: ${error.message}`,
        citations: [],
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
        currentUser={currentUser}
        onOpenAuthModal={() => setIsAuthModalOpen(true)}
        onOpenFactsModal={() => setIsFactsModalOpen(true)}
      />

      {/* Main Content Area */}
      <div className="flex-1 md:ml-[260px] flex flex-col h-full relative overflow-hidden">
        <Header
          onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
          currentUser={currentUser}
          onOpenAuthModal={() => setIsAuthModalOpen(true)}
          onLogout={handleLogout}
        />

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
                    <span className="text-sm text-gray-400">
                      RAG đang tra cứu cẩm nang du lịch & suy nghĩ...
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Input */}
        <ChatInput onSendMessage={handleSendMessage} isLoading={isLoading} />
      </div>

      {/* Modals */}
      <AuthModal
        isOpen={isAuthModalOpen}
        onClose={() => setIsAuthModalOpen(false)}
        onAuthSuccess={(user) => setCurrentUser(user)}
      />

      <UserFactsModal
        isOpen={isFactsModalOpen}
        onClose={() => setIsFactsModalOpen(false)}
      />
    </div>
  );
}
