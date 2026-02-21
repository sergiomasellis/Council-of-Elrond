import { SparklesIcon } from './Icons';
import Markdown from './Markdown';
import './Stage3.css';

export default function Stage3({ finalResponse, isAnimating = false }) {
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
          <Markdown isAnimating={isAnimating}>{finalResponse.response}</Markdown>
        </div>
      </div>
    </div>
  );
}
