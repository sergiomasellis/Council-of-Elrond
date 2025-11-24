import Stage1 from './Stage1';
import Stage2 from './Stage2';
import Stage3 from './Stage3';
import { UserIcon, BotIcon, SparklesIcon } from './Icons';
import Markdown from './Markdown';

export default function MessageBubble({ message }) {
    const isUser = message.role === 'user';

    return (
        <div className={`message-group ${isUser ? 'user' : 'assistant'}`}>
            <div className="message-avatar">
                {isUser ? <UserIcon className="avatar-icon" /> : <BotIcon className="avatar-icon" />}
            </div>

            <div className="message-body">
                <div className="message-header">
                    <span className="message-author">{isUser ? 'You' : 'LLM Council'}</span>
                </div>

                {isUser ? (
                    <div className="message-content user-content">
                        <Markdown>{message.content}</Markdown>
                    </div>
                ) : (
                    <div className="message-content assistant-content">
                        {/* Stage 1 */}
                        {message.loading?.stage1 && (
                            <div className="stage-loading">
                                <div className="spinner"></div>
                                <span>Consulting individual agents...</span>
                            </div>
                        )}
                        {message.stage1 && <Stage1 responses={message.stage1} />}

                        {/* Stage 2 */}
                        {message.loading?.stage2 && (
                            <div className="stage-loading">
                                <div className="spinner"></div>
                                <span>Agents are peer-reviewing responses...</span>
                            </div>
                        )}
                        {message.stage2 && (
                            <Stage2
                                rankings={message.stage2}
                                labelToModel={message.metadata?.label_to_model}
                                aggregateRankings={message.metadata?.aggregate_rankings}
                            />
                        )}

                        {/* Stage 3 */}
                        {message.loading?.stage3 && (
                            <div className="stage-loading">
                                <SparklesIcon className="icon-spin" />
                                <span>Synthesizing final verdict...</span>
                            </div>
                        )}
                        {message.stage3 && <Stage3 finalResponse={message.stage3} />}
                    </div>
                )}
            </div>
        </div>
    );
}
