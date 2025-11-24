import ReactMarkdown from 'react-markdown';
import { SparklesIcon } from './Icons';
import './Stage3.css';

export default function Stage3({ finalResponse }) {
  if (!finalResponse) {
    return null;
  }

  const modelName = finalResponse.model.split('/')[1] || finalResponse.model;

  return (
    <div className="stage stage3">
      <div className="final-verdict-header">
        <SparklesIcon className="verdict-icon" />
        <h3>Final Verdict</h3>
      </div>

      <div className="final-response-card">
        <div className="chairman-badge">
          <span>Synthesized by <strong>{modelName}</strong></span>
        </div>
        <div className="final-text markdown-content">
          <ReactMarkdown>{finalResponse.response}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
