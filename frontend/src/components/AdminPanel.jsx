import { useState, useEffect, useMemo } from 'react';
import { CloseIcon, SearchIcon } from './Icons';
import { api } from '../api';
import './AdminPanel.css';

export default function AdminPanel({ onClose }) {
  const [availableModels, setAvailableModels] = useState([]);
  const [councilModels, setCouncilModels] = useState([]);
  const [chairmanModel, setChairmanModel] = useState('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState(null);

  useEffect(() => {
    Promise.all([api.getAvailableModels(), api.getConfig()])
      .then(([modelsData, config]) => {
        const models = (modelsData.data || []).sort((a, b) =>
          a.id.localeCompare(b.id)
        );
        setAvailableModels(models);
        setCouncilModels(config.council_models);
        setChairmanModel(config.chairman_model);
      })
      .catch((err) => {
        console.error('Failed to load admin data:', err);
        setFeedback({ type: 'error', text: 'Failed to load configuration' });
      })
      .finally(() => setLoading(false));
  }, []);

  const filteredModels = useMemo(() => {
    if (!search.trim()) return availableModels;
    const q = search.toLowerCase();
    return availableModels.filter(
      (m) =>
        m.id.toLowerCase().includes(q) ||
        (m.name && m.name.toLowerCase().includes(q))
    );
  }, [availableModels, search]);

  const councilSet = useMemo(() => new Set(councilModels), [councilModels]);

  const toggleModel = (modelId) => {
    setCouncilModels((prev) =>
      prev.includes(modelId)
        ? prev.filter((id) => id !== modelId)
        : [...prev, modelId]
    );
    setFeedback(null);
  };

  const removeModel = (modelId) => {
    setCouncilModels((prev) => prev.filter((id) => id !== modelId));
    setFeedback(null);
  };

  const handleSave = async () => {
    if (councilModels.length < 2) {
      setFeedback({ type: 'error', text: 'At least 2 council models required' });
      return;
    }
    setSaving(true);
    setFeedback(null);
    try {
      await api.updateConfig(councilModels, chairmanModel);
      setFeedback({ type: 'success', text: 'Configuration saved' });
    } catch (err) {
      setFeedback({ type: 'error', text: err.message });
    } finally {
      setSaving(false);
    }
  };

  const formatContext = (len) => {
    if (!len) return '';
    if (len >= 1000000) return `${(len / 1000000).toFixed(1)}M ctx`;
    if (len >= 1000) return `${(len / 1000).toFixed(0)}K ctx`;
    return `${len} ctx`;
  };

  if (loading) {
    return (
      <div className="admin-panel">
        <div className="admin-header">
          <h2>Council Configuration</h2>
          <button className="admin-close-btn" onClick={onClose}>
            <CloseIcon className="icon-sm" />
          </button>
        </div>
        <div className="admin-loading">Loading models...</div>
      </div>
    );
  }

  return (
    <div className="admin-panel">
      <div className="admin-header">
        <h2>Council Configuration</h2>
        <button className="admin-close-btn" onClick={onClose}>
          <CloseIcon className="icon-sm" />
        </button>
      </div>

      <div className="admin-body">
        {/* Chairman */}
        <div className="admin-section">
          <h3>Chairman Model</h3>
          <label>The model that synthesizes the final answer</label>
          <select
            className="chairman-select"
            value={chairmanModel}
            onChange={(e) => {
              setChairmanModel(e.target.value);
              setFeedback(null);
            }}
          >
            {availableModels.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name || m.id}
              </option>
            ))}
          </select>
        </div>

        {/* Council Members */}
        <div className="admin-section">
          <h3>Council Members ({councilModels.length})</h3>
          <label>Models that provide individual responses and peer rankings</label>

          <div className="selected-models">
            {councilModels.map((id) => (
              <span key={id} className="model-chip">
                {id}
                <button onClick={() => removeModel(id)} title="Remove">&times;</button>
              </span>
            ))}
          </div>

          <div className="model-search">
            <SearchIcon className="search-icon" />
            <input
              type="text"
              placeholder="Search models..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          <div className="model-list">
            {filteredModels.length === 0 ? (
              <div className="model-list-empty">No models match your search</div>
            ) : (
              filteredModels.map((m) => (
                <label key={m.id} className="model-list-item">
                  <input
                    type="checkbox"
                    checked={councilSet.has(m.id)}
                    onChange={() => toggleModel(m.id)}
                  />
                  <div className="model-info">
                    <div className="model-name">{m.name || m.id}</div>
                    <div className="model-id">{m.id}</div>
                  </div>
                  <span className="model-context">
                    {formatContext(m.context_length)}
                  </span>
                </label>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="admin-footer">
        {feedback && (
          <span className={`admin-feedback ${feedback.type}`}>
            {feedback.text}
          </span>
        )}
        <button
          className="admin-save-btn"
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? 'Saving...' : 'Save'}
        </button>
      </div>
    </div>
  );
}
