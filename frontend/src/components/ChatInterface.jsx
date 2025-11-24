import { useRef, useEffect } from 'react';
import MessageBubble from './MessageBubble';
import ChatInput from './ChatInput';
import { BrainIcon } from './Icons';
import './ChatInterface.css';

export default function ChatInterface({
  conversation,
  onSendMessage,
  isLoading,
}) {
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [conversation]);

  if (!conversation) {
    return (
      <div className="chat-interface">
        <div className="empty-state">
          <div className="empty-state-icon">
            <BrainIcon className="icon-xl" />
          </div>
          <h2>Welcome to LLM Council</h2>
          <p>Consult a panel of AI experts for comprehensive answers.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-interface">
      <div className="messages-container">
        {conversation.messages.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">
              <BrainIcon className="icon-xl" />
            </div>
            <h2>Start a conversation</h2>
            <p>Ask a question to consult the LLM Council</p>
          </div>
        ) : (
          conversation.messages.map((msg, index) => (
            <MessageBubble key={index} message={msg} />
          ))
        )}

        {isLoading && !conversation.messages[conversation.messages.length - 1]?.loading && (
          <div className="loading-indicator">
            <div className="spinner"></div>
            <span>Consulting the council...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <ChatInput onSendMessage={onSendMessage} isLoading={isLoading} />
    </div>
  );
}
