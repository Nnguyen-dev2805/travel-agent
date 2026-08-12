import React, { useCallback, useEffect, useState } from 'react';
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
  getUserSessions,
  getSessionHistory,
  deleteSessionHistory,
  getStoredGuestSessions,
  saveGuestSession,
  deleteGuestSession,
} from './services/api';

export default function App() {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  // User Auth & Modal States
  const [currentUser, setCurrentUser] = useState(null);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [isFactsModalOpen, setIsFactsModalOpen] = useState(false);

  // Active Chat Session ID & User Sessions List
  const [sessionId, setSessionId] = useState(getStoredSessionId());
  const [sessions, setSessions] = useState([]);

  // Fetch list of user/guest sessions
  const refreshSessions = useCallback(async () => {
    if (currentUser) {
      const userSessions = await getUserSessions();
      setSessions(userSessions || []);
    } else {
      const guestSessions = getStoredGuestSessions();
      setSessions(guestSessions || []);
    }
  }, [currentUser]);

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

  // Refresh session list when currentUser changes or mounts
  useEffect(() => {
    refreshSessions();
  }, [currentUser, refreshSessions]);

  // Load chat history whenever active sessionId changes
  useEffect(() => {
    async function loadHistory() {
      if (sessionId) {
        const history = await getSessionHistory(sessionId);
        if (Array.isArray(history) && history.length > 0) {
          setMessages(
            history.map((msg) => ({
              role: msg.role,
              content: msg.content,
              citations: [],
            }))
          );
        } else {
          setMessages([]);
        }
      }
    }
    loadHistory();
  }, [sessionId]);

  const handleNewChat = () => {
    const newSid = createNewSessionId();
    setSessionId(newSid);
    setMessages([]);
  };

  const handleSelectSession = (selectedSid) => {
    if (selectedSid !== sessionId) {
      localStorage.setItem('travel_chat_session_id', selectedSid);
      setSessionId(selectedSid);
    }
  };

  const handleDeleteSession = async (targetSid) => {
    if (currentUser) {
      await deleteSessionHistory(targetSid);
    } else {
      deleteGuestSession(targetSid);
    }

    if (targetSid === sessionId) {
      handleNewChat();
    }
    refreshSessions();
  };

  const handleLogout = () => {
    logoutUser();
    setCurrentUser(null);
    setSessions([]);
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
        localStorage.setItem('travel_chat_session_id', data.session_id);
        setSessionId(data.session_id);
      }

      // Save guest session locally if not logged in
      if (!currentUser) {
        saveGuestSession(sessionId, userText);
      }

      // Refresh recent sessions list after message sent
      refreshSessions();
    } catch (error) {
      const errorMessage = {
        role: 'assistant',
        content: `❌ Connection error: ${error.message}`,
        citations: [],
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-screen w-full bg-[#ffffff] text-[#0d0d0d] overflow-hidden antialiased font-[-apple-system,BlinkMacSystemFont,'Segoe_UI',Roboto,sans-serif] relative">
      {/* Sidebar Overlay Backdrop (Chỉ hiển thị trên Mobile) */}
      {isSidebarOpen && (
        <div
          onClick={() => setIsSidebarOpen(false)}
          className="fixed inset-0 bg-black/20 backdrop-blur-[1px] z-40 md:hidden animate-in fade-in duration-200"
        />
      )}

      {/* Sidebar Drawer */}
      <Sidebar
        isOpen={isSidebarOpen}
        onToggle={() => setIsSidebarOpen(!isSidebarOpen)}
        onNewChat={() => {
          handleNewChat();
          if (window.innerWidth < 768) setIsSidebarOpen(false);
        }}
        currentUser={currentUser}
        onOpenAuthModal={() => {
          setIsAuthModalOpen(true);
          if (window.innerWidth < 768) setIsSidebarOpen(false);
        }}
        onOpenFactsModal={() => {
          setIsFactsModalOpen(true);
          if (window.innerWidth < 768) setIsSidebarOpen(false);
        }}
        onLogout={handleLogout}
        sessions={sessions}
        activeSessionId={sessionId}
        onSelectSession={(sid) => {
          handleSelectSession(sid);
          if (window.innerWidth < 768) setIsSidebarOpen(false);
        }}
        onDeleteSession={handleDeleteSession}
      />

      {/* Main Canvas (Level 1) */}
      <div className={`flex-1 flex flex-col relative h-full overflow-hidden bg-[#ffffff] transition-all duration-300 ${
        isSidebarOpen ? 'md:ml-[260px]' : 'md:ml-[56px]'
      }`}>
        {/* Top Header */}
        <Header
          isSidebarOpen={isSidebarOpen}
          onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
          currentUser={currentUser}
          onOpenAuthModal={() => setIsAuthModalOpen(true)}
          onLogout={handleLogout}
        />

        {/* Messages or Welcome View */}
        <div className="flex-1 overflow-y-auto custom-scrollbar flex flex-col pt-0">
          {messages.length === 0 ? (
            <WelcomeView
              currentUser={currentUser}
              onSelectCard={handleSendMessage}
              onSendMessage={handleSendMessage}
            />
          ) : (
            <div className="pb-8 space-y-6 pt-4">
              {messages.map((msg, idx) => (
                <ChatMessage key={idx} message={msg} />
              ))}
              {isLoading && (
                <div className="w-full max-w-[768px] mx-auto px-4 md:px-0 py-3">
                  <div className="flex gap-3 items-center">
                    <div className="w-8 h-8 rounded-full bg-[#0d0d0d] flex items-center justify-center text-white text-xs">
                      <span className="material-symbols-outlined text-sm animate-spin">
                        sync
                      </span>
                    </div>
                    <span className="text-xs text-[#5d5d5d]">
                      VietraAI is thinking...
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Bottom Input Bar (Only displayed during active chat thread) */}
        {messages.length > 0 && (
          <ChatInput onSendMessage={handleSendMessage} isLoading={isLoading} />
        )}
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
