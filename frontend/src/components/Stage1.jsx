import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { BotIcon, ChevronDownIcon, ChevronRightIcon } from './Icons';
import './Stage1.css';

export default function Stage1({ responses }) {
  const [activeTab, setActiveTab] = useState(0);
  const [isExpanded, setIsExpanded] = useState(false);

  if (!responses || responses.length === 0) {
    return null;
  }

  return (
    <div className="stage stage1">
      <div className="stage-header">
        <div className="stage-icon-wrapper">
          <BotIcon className="stage-icon" />
        </div>
        <h3 className="stage-title">Stage 1: Individual Perspectives</h3>
      </div>

      <div className="details-toggle" onClick={() => setIsExpanded(!isExpanded)}>
        {isExpanded ? <ChevronDownIcon className="icon-xs" /> : <ChevronRightIcon className="icon-xs" />}
        <span>{isExpanded ? 'Hide Individual Responses' : 'Show Individual Responses'}</span>
      </div>

      {isExpanded && (
        <div className="stage-content-wrapper">
          <div className="agent-selector">
            {responses.map((resp, index) => {
              const modelName = resp.model.split('/')[1] || resp.model;
              return (
                <button
                  key={index}
                  className={`agent-chip ${activeTab === index ? 'active' : ''}`}
                  onClick={() => setActiveTab(index)}
                >
                  <div className="agent-avatar-small">{modelName[0].toUpperCase()}</div>
                  <span className="agent-name">{modelName}</span>
                </button>
              );
            })}
          </div>

          <div className="agent-response-card">
            <div className="response-header">
              <span className="model-badge">{responses[activeTab].model}</span>
            </div>
            <div className="response-text markdown-content">
              <ReactMarkdown>{responses[activeTab].response}</ReactMarkdown>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
