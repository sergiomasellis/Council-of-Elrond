import { useState } from 'react';
import { TrophyIcon, ChevronDownIcon, ChevronRightIcon } from './Icons';
import Markdown from './Markdown';
import './Stage2.css';

function deAnonymizeText(text, labelToModel) {
  if (!labelToModel) return text;

  let result = text;
  Object.entries(labelToModel).forEach(([label, model]) => {
    const modelShortName = model.split('/')[1] || model;
    result = result.replace(new RegExp(label, 'g'), `**${modelShortName}**`);
  });
  return result;
}

export default function Stage2({ rankings, labelToModel, aggregateRankings }) {
  const [activeTab, setActiveTab] = useState(0);
  const [showDetails, setShowDetails] = useState(false);

  if (!rankings || rankings.length === 0) {
    return null;
  }

  return (
    <div className="stage stage2">
      <div className="stage-header">
        <div className="stage-icon-wrapper">
          <TrophyIcon className="stage-icon" />
        </div>
        <h3 className="stage-title">Stage 2: Peer Review & Ranking</h3>
      </div>

      {aggregateRankings && aggregateRankings.length > 0 && (
        <div className="leaderboard">
          <h4 className="leaderboard-title">Consensus Ranking</h4>
          <div className="leaderboard-list">
            {aggregateRankings.map((agg, index) => {
              const modelName = agg.model.split('/')[1] || agg.model;
              const isWinner = index === 0;
              return (
                <div key={index} className={`leaderboard-item ${isWinner ? 'winner' : ''}`}>
                  <div className="rank-badge">{index + 1}</div>
                  <div className="rank-info">
                    <span className="rank-model-name">{modelName}</span>
                    <div className="rank-bar-container">
                      <div
                        className="rank-bar"
                        style={{ width: `${(1 - (agg.average_rank / rankings.length)) * 100}%` }}
                      ></div>
                    </div>
                  </div>
                  <div className="rank-stats">
                    <span className="rank-score">Avg Rank: {agg.average_rank.toFixed(1)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="details-toggle" onClick={() => setShowDetails(!showDetails)}>
        {showDetails ? <ChevronDownIcon className="icon-xs" /> : <ChevronRightIcon className="icon-xs" />}
        <span>{showDetails ? 'Hide Peer Reviews' : 'Show Peer Reviews'}</span>
      </div>

      {showDetails && (
        <div className="reviews-section">
          <div className="agent-selector">
            {rankings.map((rank, index) => {
              const modelName = rank.model.split('/')[1] || rank.model;
              return (
                <button
                  key={index}
                  className={`agent-chip ${activeTab === index ? 'active' : ''}`}
                  onClick={() => setActiveTab(index)}
                >
                  <span className="agent-name">{modelName}</span>
                </button>
              );
            })}
          </div>

          <div className="review-card">
            <div className="review-content markdown-content">
              <Markdown>
                {deAnonymizeText(rankings[activeTab].ranking, labelToModel)}
              </Markdown>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
