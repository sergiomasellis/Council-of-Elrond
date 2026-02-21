import { useState, useEffect, useCallback, useRef } from 'react';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import { api } from './api';
import './App.css';

function App() {
  const [conversations, setConversations] = useState([]);
  const [currentConversationId, setCurrentConversationId] = useState(null);
  const [currentConversation, setCurrentConversation] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [theme, setTheme] = useState('dark');
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const currentConversationIdRef = useRef(null);

  useEffect(() => {
    currentConversationIdRef.current = currentConversationId;
  }, [currentConversationId]);

  useEffect(() => {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme) {
      setTheme(savedTheme);
      document.documentElement.setAttribute('data-theme', savedTheme);
    } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
      setTheme('light');
      document.documentElement.setAttribute('data-theme', 'light');
    }
  }, []);

  const toggleTheme = () => {
    const newTheme = theme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme);
    localStorage.setItem('theme', newTheme);
    document.documentElement.setAttribute('data-theme', newTheme);
  };

  const openSidebar = () => setIsSidebarOpen(true);
  const closeSidebar = () => setIsSidebarOpen(false);
  const toggleSidebar = () => setIsSidebarOpen((prev) => !prev);

  useEffect(() => {
    loadConversations();
  }, []);

  useEffect(() => {
    if (currentConversationId) {
      loadConversation(currentConversationId);
    }
  }, [currentConversationId]);

  const loadConversations = async () => {
    try {
      const convs = await api.listConversations();
      setConversations(convs);
    } catch (error) {
      console.error('Failed to load conversations:', error);
    }
  };

  // Helper: immutably update the last assistant message
  const updateLastAssistant = useCallback((updater) => {
    setCurrentConversation((prev) => {
      if (!prev) return prev;
      const lastIdx = prev.messages.length - 1;
      const lastMsg = prev.messages[lastIdx];
      if (!lastMsg || lastMsg.role !== 'assistant') return prev;
      const updated = updater(lastMsg);
      const messages = prev.messages.slice();
      messages[lastIdx] = updated;
      return { ...prev, messages };
    });
  }, []);

  // Shared event handler for both initial stream and reconnection
  const handleStreamEvent = useCallback((eventType, event) => {
    switch (eventType) {
      case 'stage1_start':
        updateLastAssistant((msg) => ({
          ...msg,
          loading: { ...msg.loading, stage1: true },
        }));
        break;

      case 'stage1_init':
        updateLastAssistant((msg) => {
          const stage1 = msg.stage1 || [];
          if (stage1.find((r) => r.model === event.data.model)) return msg;
          return {
            ...msg,
            stage1: [...stage1, event.data],
            loading: { ...msg.loading, stage1: false },
          };
        });
        break;

      case 'stage1_chunk':
        updateLastAssistant((msg) => {
          if (!msg.stage1) return msg;
          return {
            ...msg,
            stage1: msg.stage1.map((r) =>
              r.model === event.model
                ? { ...r, response: r.response + event.chunk }
                : r
            ),
          };
        });
        break;

      case 'stage1_complete':
        updateLastAssistant((msg) => ({
          ...msg,
          stage1: event.data,
          loading: { ...msg.loading, stage1: false },
        }));
        break;

      case 'stage2_start':
        updateLastAssistant((msg) => ({
          ...msg,
          loading: { ...msg.loading, stage2: true },
        }));
        break;

      case 'stage2_map':
        updateLastAssistant((msg) => ({
          ...msg,
          metadata: { ...(msg.metadata || {}), label_to_model: event.data },
        }));
        break;

      case 'stage2_init':
        updateLastAssistant((msg) => {
          const stage2 = msg.stage2 || [];
          if (stage2.find((r) => r.model === event.data.model)) return msg;
          return {
            ...msg,
            stage2: [...stage2, event.data],
            loading: { ...msg.loading, stage2: false },
          };
        });
        break;

      case 'stage2_chunk':
        updateLastAssistant((msg) => {
          if (!msg.stage2) return msg;
          return {
            ...msg,
            stage2: msg.stage2.map((r) =>
              r.model === event.model
                ? { ...r, ranking: r.ranking + event.chunk }
                : r
            ),
          };
        });
        break;

      case 'stage2_complete':
        updateLastAssistant((msg) => ({
          ...msg,
          stage2: event.data,
          metadata: event.metadata,
          loading: { ...msg.loading, stage2: false },
        }));
        break;

      case 'stage3_start':
        updateLastAssistant((msg) => ({
          ...msg,
          loading: { ...msg.loading, stage3: true },
        }));
        break;

      case 'stage3_init':
        updateLastAssistant((msg) => ({
          ...msg,
          stage3: event.data,
          loading: { ...msg.loading, stage3: false },
        }));
        break;

      case 'stage3_chunk':
        updateLastAssistant((msg) => {
          if (!msg.stage3) return msg;
          return {
            ...msg,
            stage3: { ...msg.stage3, response: msg.stage3.response + event.chunk },
          };
        });
        break;

      case 'stage3_complete':
        updateLastAssistant((msg) => ({
          ...msg,
          stage3: event.data,
          loading: { ...msg.loading, stage3: false },
        }));
        break;

      case 'title_complete':
        loadConversations();
        break;

      case 'complete':
        loadConversations();
        setIsLoading(false);
        break;

      case 'error':
        console.error('Stream error:', event.message);
        updateLastAssistant((msg) => ({
          ...msg,
          loading: { stage1: false, stage2: false, stage3: false },
          stage3: msg.stage3 || {
            model: 'error',
            response: `**Error:** ${event.message || 'The council encountered an error. Please try again.'}`,
          },
        }));
        setIsLoading(false);
        break;

      default:
        console.log('Unknown event type:', eventType);
    }
  }, [updateLastAssistant]);

  // Reconnect to an active job for a conversation
  const reconnectToJob = useCallback(async (conversationId) => {
    setIsLoading(true);

    // Ensure the last message has loading state for the stream
    setCurrentConversation((prev) => {
      if (!prev) return prev;
      const lastIdx = prev.messages.length - 1;
      const lastMsg = prev.messages[lastIdx];
      if (!lastMsg || lastMsg.role !== 'assistant') return prev;
      // Add loading state if not present
      if (lastMsg.loading) return prev;
      const messages = prev.messages.slice();
      messages[lastIdx] = {
        ...lastMsg,
        loading: { stage1: false, stage2: false, stage3: false },
      };
      return { ...prev, messages };
    });

    try {
      await api.reconnectJobStream(conversationId, 0, handleStreamEvent);
      setIsLoading(false);
    } catch (error) {
      console.error('Failed to reconnect to job:', error);
      setIsLoading(false);
    }
  }, [handleStreamEvent]);

  const loadConversation = async (id) => {
    try {
      const conv = await api.getConversation(id);
      setCurrentConversation(conv);

      // Check if the last assistant message is incomplete (has a non-terminal status)
      const lastMsg = conv.messages[conv.messages.length - 1];
      if (
        lastMsg &&
        lastMsg.role === 'assistant' &&
        lastMsg.status &&
        lastMsg.status !== 'complete' &&
        lastMsg.status !== 'error'
      ) {
        // Check if there's an active job to reconnect to
        try {
          const jobStatus = await api.getJobStatus(id);
          if (jobStatus.active) {
            reconnectToJob(id);
          }
        } catch (error) {
          console.error('Failed to check job status:', error);
        }
      }
    } catch (error) {
      console.error('Failed to load conversation:', error);
    }
  };

  const handleNewConversation = async () => {
    try {
      const newConv = await api.createConversation();
      setConversations([
        { id: newConv.id, created_at: newConv.created_at, message_count: 0 },
        ...conversations,
      ]);
      setCurrentConversationId(newConv.id);
      closeSidebar();
    } catch (error) {
      console.error('Failed to create conversation:', error);
    }
  };

  const handleSelectConversation = (id) => {
    setCurrentConversationId(id);
    closeSidebar();
  };

  const handleDeleteConversation = async (id, e) => {
    e.stopPropagation();
    if (!window.confirm('Are you sure you want to delete this conversation?')) return;

    try {
      await api.deleteConversation(id);
      setConversations(conversations.filter((c) => c.id !== id));
      if (currentConversationId === id) {
        setCurrentConversationId(null);
        setCurrentConversation(null);
      }
      closeSidebar();
    } catch (error) {
      console.error('Failed to delete conversation:', error);
    }
  };

  const handleSendMessage = async (content) => {
    if (!currentConversationId) return;

    setIsLoading(true);
    try {
      // Optimistically add user message to UI
      const userMessage = { role: 'user', content };
      setCurrentConversation((prev) => ({
        ...prev,
        messages: [...prev.messages, userMessage],
      }));

      // Create a partial assistant message that will be updated progressively
      const assistantMessage = {
        role: 'assistant',
        stage1: null,
        stage2: null,
        stage3: null,
        metadata: null,
        loading: {
          stage1: true,
          stage2: false,
          stage3: false,
        },
      };

      setCurrentConversation((prev) => ({
        ...prev,
        messages: [...prev.messages, assistantMessage],
      }));

      // Send message with streaming
      try {
        await api.sendMessageStream(currentConversationId, content, handleStreamEvent);
      } catch (error) {
        if (error.status === 409) {
          // Job already running — reconnect instead
          await reconnectToJob(currentConversationId);
          return;
        }
        throw error;
      }

      // Safety net
      setIsLoading(false);
    } catch (error) {
      console.error('Failed to send message:', error);
      setCurrentConversation((prev) => ({
        ...prev,
        messages: prev.messages.slice(0, -2),
      }));
      setIsLoading(false);
    }
  };

  return (
    <div className="app">
      <Sidebar
        conversations={conversations}
        currentConversationId={currentConversationId}
        onSelectConversation={handleSelectConversation}
        onNewConversation={handleNewConversation}
        onDeleteConversation={handleDeleteConversation}
        theme={theme}
        toggleTheme={toggleTheme}
        isOpen={isSidebarOpen}
        onClose={closeSidebar}
      />
      <div
        className={`sidebar-backdrop ${isSidebarOpen ? 'show' : ''}`}
        onClick={closeSidebar}
        aria-hidden="true"
      />
      <ChatInterface
        conversation={currentConversation}
        onSendMessage={handleSendMessage}
        isLoading={isLoading}
        onToggleSidebar={toggleSidebar}
      />
    </div>
  );
}

export default App;
