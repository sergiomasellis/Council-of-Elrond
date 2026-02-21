import { useState, useRef, useEffect } from 'react';
import { SendIcon, MicIcon } from './Icons';
import './ChatInterface.css';

export default function ChatInput({ onSendMessage, isLoading }) {
    const [input, setInput] = useState('');
    const [isListening, setIsListening] = useState(false);
    const textareaRef = useRef(null);
    const recognitionRef = useRef(null);
    const MAX_CHARS = 3000;

    useEffect(() => {
        if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            recognitionRef.current = new SpeechRecognition();
            recognitionRef.current.continuous = true;
            recognitionRef.current.interimResults = false;

            recognitionRef.current.onresult = (event) => {
                let finalTranscript = '';
                for (let i = event.resultIndex; i < event.results.length; ++i) {
                    if (event.results[i].isFinal) {
                        finalTranscript += event.results[i][0].transcript;
                    }
                }
                if (finalTranscript) {
                    setInput(prev => {
                        const newValue = prev + (prev.length > 0 && !prev.endsWith(' ') ? ' ' : '') + finalTranscript;
                        return newValue.slice(0, MAX_CHARS);
                    });

                    // Trigger resize
                    if (textareaRef.current) {
                        textareaRef.current.style.height = 'auto';
                        textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
                    }
                }
            };

            recognitionRef.current.onerror = (event) => {
                console.error('Speech recognition error', event.error);
                setIsListening(false);
            };

            recognitionRef.current.onend = () => {
                setIsListening(false);
            };
        }
    }, []);

    const toggleListening = () => {
        if (!recognitionRef.current) {
            alert('Speech recognition is not supported in this browser.');
            return;
        }

        if (isListening) {
            recognitionRef.current.stop();
            setIsListening(false);
        } else {
            recognitionRef.current.start();
            setIsListening(true);
        }
    };

    const handleSubmit = (e) => {
        e.preventDefault();
        if (input.trim() && !isLoading) {
            onSendMessage(input);
            setInput('');
            if (textareaRef.current) {
                textareaRef.current.style.height = 'auto';
            }
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit(e);
        }
    };

    const handleInput = (e) => {
        const target = e.target;
        const value = target.value;
        if (value.length <= MAX_CHARS) {
            target.style.height = 'auto';
            target.style.height = `${Math.min(target.scrollHeight, 200)}px`;
            setInput(value);
        }
    };

    return (
        <form className="input-form" onSubmit={handleSubmit}>
            <div className={`input-wrapper ${isListening ? 'listening' : ''}`}>
                <textarea
                    ref={textareaRef}
                    className="message-input"
                    placeholder="Ask the council..."
                    value={input}
                    onChange={handleInput}
                    onKeyDown={handleKeyDown}
                    disabled={isLoading}
                    rows={1}
                />
                <div className="input-actions">
                    <span className={`char-counter ${input.length >= MAX_CHARS ? 'limit-reached' : ''}`}>
                        {input.length}/{MAX_CHARS}
                    </span>
                    <button
                        type="button"
                        className={`action-button mic-button ${isListening ? 'active' : ''}`}
                        onClick={toggleListening}
                        disabled={isLoading}
                        title={isListening ? "Stop dictation" : "Start dictation"}
                    >
                        <MicIcon className="icon-mic" />
                    </button>
                    <button
                        type="submit"
                        className="action-button send-button"
                        disabled={!input.trim() || isLoading}
                        title="Send message"
                    >
                        <SendIcon className="icon-send" />
                    </button>
                </div>
            </div>
            <div className="input-footer">
                <small>The Council of Elrond can make mistakes. Verify important information.</small>
            </div>
        </form>
    );
}
