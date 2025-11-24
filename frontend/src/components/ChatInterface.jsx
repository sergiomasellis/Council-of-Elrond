import { useRef, useEffect } from 'react';
import MessageBubble from './MessageBubble';
import ChatInput from './ChatInput';
import { BrainIcon, MenuIcon } from './Icons';
import PixelBlast from './PixelBlast';
import './ChatInterface.css';

export default function ChatInterface({
  conversation,
  onSendMessage,
  isLoading,
  onToggleSidebar,
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
        <button className="mobile-menu-btn" onClick={onToggleSidebar} aria-label="Open menu">
          <MenuIcon className="icon-sm" />
        </button>
        <div className="empty-state">
          <div className="empty-visual">
            <PixelBlast
              variant="circle"
              pixelSize={3}
              color="#0f5c4f"
              patternScale={2}
              patternDensity={0.55}
              pixelSizeJitter={1.25}
              enableRipples
              rippleSpeed={0.4}
              rippleThickness={0.12}
              rippleIntensityScale={1.5}
              liquid
              liquidStrength={0.12}
              liquidRadius={1.2}
              liquidWobbleSpeed={5}
              speed={2.6}
              edgeFade={0.25}
              transparent
            />
          </div>
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
      <button className="mobile-menu-btn" onClick={onToggleSidebar} aria-label="Open menu">
        <MenuIcon className="icon-sm" />
      </button>
      <div className="messages-container">
        {conversation.messages.length === 0 ? (
          <div className="empty-state">
            <div className="empty-visual">
            <PixelBlast
              variant="circle"
              pixelSize={3}
              color="#0f5c4f"
              patternScale={3}
              patternDensity={0.55}
              pixelSizeJitter={1.25}
              enableRipples
              rippleSpeed={0.4}
              rippleThickness={0.12}
              rippleIntensityScale={1.5}
              liquid
              liquidStrength={0.12}
              liquidRadius={1.2}
              liquidWobbleSpeed={5}
              speed={2.6}
              edgeFade={0.25}
              transparent
            />
            </div>
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
