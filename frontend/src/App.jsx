import React, { useState, useEffect } from 'react';
import Header from './components/layout/Header';
import Sidebar from './components/layout/Sidebar';
import ChatPanel from './components/chat/ChatPanel';
import WelcomeView from './components/welcome/WelcomeView';
import LoginModal from './components/auth/LoginModal';

import { clearToken, isAuthenticated } from './services/auth';
import {
  listConversations,
  deleteConversation,
  listMessages,
  postChatMessage,
} from './services/chat';

export default function App() {
  const [isAuth, setIsAuth] = useState(isAuthenticated());
  const [conversations, setConversations] = useState([]);
  const [activeConversationId, setActiveConversationId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(() => {
    if (typeof window !== 'undefined' && window.localStorage) {
      return localStorage.getItem('travel_agent_sidebar_collapsed') === 'true';
    }
    return false;
  });

  const handleToggleSidebarCollapse = () => {
    setIsSidebarCollapsed((prev) => {
      const next = !prev;
      if (typeof window !== 'undefined' && window.localStorage) {
        localStorage.setItem('travel_agent_sidebar_collapsed', String(next));
      }
      return next;
    });
  };

  // 1. Fetch conversations when authenticated
  const loadConversations = async (preferredConvId = null) => {
    try {
      const data = await listConversations();
      setConversations(data || []);

      if (data && data.length > 0) {
        const targetId = preferredConvId || activeConversationId;
        if (targetId && data.some((c) => c.conversation_id === targetId)) {
          handleSelectConversation(targetId);
        }
      }
    } catch (err) {
      console.error('Lỗi tải conversations:', err);
    }
  };

  useEffect(() => {
    if (isAuth) {
      loadConversations();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuth]);

  // Listen for 401 unauthorized events to force clean logout
  useEffect(() => {
    const handleUnauthorized = () => {
      clearToken();
      setIsAuth(false);
      setConversations([]);
      setActiveConversationId(null);
      setMessages([]);
    };
    if (typeof window !== "undefined") {
      window.addEventListener("auth:unauthorized", handleUnauthorized);
      return () => window.removeEventListener("auth:unauthorized", handleUnauthorized);
    }
  }, []);

  // Global ⌘K / Ctrl+K keyboard shortcut to start a new chat
  useEffect(() => {
    const handleGlobalKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        handleNewChat();
      }
    };
    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, []);

  // 2. Select conversation and load message history
  const handleSelectConversation = async (convId) => {
    setActiveConversationId(convId);
    try {
      const msgs = await listMessages(convId);
      setMessages(msgs || []);
    } catch (err) {
      console.error('Lỗi mở conversation:', err);
    }
  };

  // 3. Start a fresh conversation
  const handleNewChat = () => {
    setActiveConversationId(null);
    setMessages([]);
  };

  // 4. Send chat message (auto-creates conversation if activeConversationId is null)
  const handleSendMessage = async (text) => {
    if (!text.trim() || isChatLoading) return;

    // Optimistic user message
    const tempUserMsg = {
      message_id: `temp_${Date.now()}`,
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);
    setIsChatLoading(true);

    try {
      const result = await postChatMessage({
        message: text,
        conversation_id: activeConversationId,
      });

      const returnedConvId = result.conversation?.conversation_id;
      if (!activeConversationId && returnedConvId) {
        setActiveConversationId(returnedConvId);
        await loadConversations(returnedConvId);
      }

      const assistantMsg = {
        message_id: result.conversation?.assistant_message_id || `asst_${Date.now()}`,
        role: 'assistant',
        content: result.reply,
        citations: result.citations || [],
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      console.error('Lỗi gửi tin nhắn:', err);
      const errorMsg = {
        message_id: `err_${Date.now()}`,
        role: 'assistant',
        content: `⚠️ Xin lỗi, đã có lỗi xảy ra: ${err.message}`,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsChatLoading(false);
    }
  };

  // 5. Select template
  const handleSelectTemplate = (template) => {
    handleSendMessage(template.prompt);
  };

  // 6. Delete conversation
  const handleDeleteConversation = async (convId) => {
    try {
      await deleteConversation(convId);
    } catch (err) {
      console.error('Lỗi xóa conversation:', err);
    }
    const remaining = conversations.filter((c) => c.conversation_id !== convId);
    setConversations(remaining);
    if (activeConversationId === convId) {
      handleNewChat();
    }
  };

  const handleLogout = () => {
    clearToken();
    setIsAuth(false);
    setConversations([]);
    handleNewChat();
  };

  // Primary Authentication Gate: unauthenticated users see login only
  if (!isAuth) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-pure-white text-graphite-ink font-sans">
        <LoginModal
          onLoginSuccess={() => {
            setIsAuth(true);
          }}
        />
      </div>
    );
  }

  return (
    <div className="h-screen w-screen flex overflow-hidden bg-pure-white text-graphite-ink font-sans">

      {/* Left Sidebar */}
      <Sidebar
        conversations={conversations}
        activeConversationId={activeConversationId}
        onSelectConversation={handleSelectConversation}
        onNewChat={handleNewChat}
        onDeleteConversation={handleDeleteConversation}
        onLogout={handleLogout}
        onLoginClick={() => setIsAuth(false)}
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
        isCollapsed={isSidebarCollapsed}
        onToggleCollapse={handleToggleSidebarCollapse}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden relative">
        <Header
          onToggleSidebar={() => setIsSidebarOpen((prev) => !prev)}
          onLoginClick={() => setIsAuth(false)}
          onLogout={handleLogout}
        />

        {/* Dynamic Main Body: WelcomeView vs Active Chat Panel */}
        {!activeConversationId && messages.length === 0 ? (
          <div className="flex-1 flex flex-col overflow-hidden">
            <WelcomeView onSelectTemplate={handleSelectTemplate} />
            <div className="p-4 max-w-[768px] w-full mx-auto pb-6">
              <ChatPanel
                messages={[]}
                onSendMessage={handleSendMessage}
                isLoading={isChatLoading}
              />
            </div>
          </div>
        ) : (
          <div className="flex-1 flex flex-col overflow-hidden">
            <ChatPanel
              messages={messages}
              onSendMessage={handleSendMessage}
              isLoading={isChatLoading}
            />
          </div>
        )}
      </div>
    </div>
  );
}
