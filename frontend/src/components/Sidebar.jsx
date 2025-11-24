import { PlusIcon, ChatIcon, BrainIcon, SunIcon, MoonIcon, TrashIcon, CloseIcon } from './Icons';
import './Sidebar.css';

export default function Sidebar({
  conversations,
  currentConversationId,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation,
  theme,
  toggleTheme,
  isOpen = false,
  onClose,
}) {
  return (
    <div className={`sidebar ${isOpen ? 'open' : ''}`}>
      <div className="sidebar-header">
        <div className="logo-area">
          <BrainIcon className="logo-icon" />
          <h1>LLM Council</h1>
        </div>
        <button className="mobile-close-btn" onClick={onClose} aria-label="Close menu">
          <CloseIcon className="icon-sm" />
        </button>
        <button className="new-conversation-btn" onClick={onNewConversation}>
          <PlusIcon className="icon-sm" />
          <span>New Chat</span>
        </button>
      </div>

      <div className="conversation-list">
        {conversations.length === 0 ? (
          <div className="no-conversations">
            <p>No conversations yet</p>
            <small>Start a new chat to consult the council</small>
          </div>
        ) : (
          conversations.map((conv) => (
            <div
              key={conv.id}
              className={`conversation-item ${conv.id === currentConversationId ? 'active' : ''
                }`}
              onClick={() => onSelectConversation(conv.id)}
            >
              <ChatIcon className="chat-icon-item" />
              <div className="conversation-info">
                <div className="conversation-title">
                  {conv.title || 'New Conversation'}
                </div>
                <div className="conversation-meta">
                  {conv.message_count} messages
                </div>
              </div>
              <button
                className="delete-btn"
                onClick={(e) => onDeleteConversation(conv.id, e)}
                title="Delete conversation"
              >
                <TrashIcon className="icon-xs" />
              </button>
            </div>
          ))
        )}
      </div>

      <div className="sidebar-footer">
        <div className="user-profile">
          <div className="user-avatar">U</div>
          <div className="user-info">
            <span className="user-name">User</span>
            <span className="user-role">Council Lead</span>
          </div>
        </div>
        <button className="theme-toggle" onClick={toggleTheme} title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}>
          {theme === 'dark' ? <SunIcon className="icon-sm" /> : <MoonIcon className="icon-sm" />}
        </button>
      </div>
    </div>
  );
}
