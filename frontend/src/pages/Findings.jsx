import { useState, useEffect } from 'react';
import { api } from '../api/client';
import FindingCard from '../components/FindingCard';
import SeverityBadge from '../components/SeverityBadge';
import { STATUS_COLORS } from '../utils/formatters';

export default function Findings() {
  const [findings, setFindings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [filters, setFilters] = useState({ severity: '', type: '', tool_name: '', status: '' });

  const loadFindings = () => {
    const params = {};
    Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });
    api.getFindings(params).then((data) => {
      setFindings(Array.isArray(data) ? data : []);
    }).catch(() => setFindings([])).finally(() => setLoading(false));
  };

  useEffect(() => { loadFindings(); }, [filters]);

  const updateStatus = async (id, status) => {
    await api.updateFindingStatus(id, status);
    if (selected?.id === id) setSelected({ ...selected, status });
    loadFindings();
  };

  const createJira = async (id) => {
    try {
      const result = await api.createJiraTicket(id);
      loadFindings();
      alert(`Jira ticket created: ${result.ticket_url || result.ticket_id}`);
    } catch (e) { alert(e.message); }
  };

  const counts = {
    critical: findings.filter((f) => f.severity === 'critical').length,
    high: findings.filter((f) => f.severity === 'high').length,
    medium: findings.filter((f) => f.severity === 'medium').length,
    low: findings.filter((f) => f.severity === 'low').length,
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Findings</h1>

      {/* Summary bar */}
      <div className="flex gap-3 mb-4">
        {Object.entries(counts).map(([sev, count]) => (
          <button key={sev} onClick={() => setFilters({ ...filters, severity: filters.severity === sev ? '' : sev })}
            className={`flex items-center gap-2 px-3 py-1.5 rounded text-sm border ${filters.severity === sev ? 'border-blue-500 bg-blue-50' : 'border-gray-200'}`}>
            <SeverityBadge severity={sev} /> <span>{count}</span>
          </button>
        ))}
      </div>

      {/* Filters */}
      <div className="flex gap-2 mb-4">
        <select value={filters.type} onChange={(e) => setFilters({ ...filters, type: e.target.value })} className="border rounded px-2 py-1 text-sm">
          <option value="">All types</option>
          {['xss', 'injection', 'auth', 'secret', 'dependency', 'config', 'crypto', 'disclosure'].map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <select value={filters.tool_name} onChange={(e) => setFilters({ ...filters, tool_name: e.target.value })} className="border rounded px-2 py-1 text-sm">
          <option value="">All tools</option>
          {['semgrep', 'gitleaks', 'trivy', 'npm_audit', 'eslint_security', 'retirejs', 'ai_analysis'].map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })} className="border rounded px-2 py-1 text-sm">
          <option value="">All statuses</option>
          {['open', 'in_progress', 'fixed', 'false_positive'].map((s) => (
            <option key={s} value={s}>{s.replace('_', ' ')}</option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Findings list */}
        <div className="lg:col-span-2 space-y-2">
          {loading ? (
            <p className="text-gray-400">Loading...</p>
          ) : findings.length === 0 ? (
            <p className="text-gray-400">No findings match the filters.</p>
          ) : (
            findings.map((f) => (
              <FindingCard key={f.id} finding={f} onClick={setSelected} onCreateJira={createJira} />
            ))
          )}
        </div>

        {/* Detail panel */}
        <div className="lg:col-span-1">
          {selected ? (
            <div className="bg-white rounded-lg shadow p-4 sticky top-4">
              <div className="flex items-center gap-2 mb-3">
                <SeverityBadge severity={selected.severity} />
                <h3 className="font-semibold text-sm flex-1">{selected.title}</h3>
              </div>

              {selected.file_path && (
                <p className="text-sm font-mono text-gray-600 mb-2">
                  {selected.file_path}:{selected.line_start || '?'}
                </p>
              )}

              {selected.description && (
                <div className="mb-3">
                  <h4 className="text-xs text-gray-500 font-medium">Description</h4>
                  <p className="text-sm">{selected.description}</p>
                </div>
              )}

              {selected.code_snippet && (
                <div className="mb-3">
                  <h4 className="text-xs text-gray-500 font-medium">Code</h4>
                  <pre className="bg-gray-900 text-green-400 text-xs p-3 rounded overflow-x-auto">{selected.code_snippet}</pre>
                </div>
              )}

              {selected.recommendation && (
                <div className="mb-3">
                  <h4 className="text-xs text-gray-500 font-medium">Recommendation</h4>
                  <p className="text-sm">{selected.recommendation}</p>
                </div>
              )}

              <div className="grid grid-cols-2 gap-2 text-xs mb-3">
                {selected.cwe_id && <div><span className="text-gray-400">CWE:</span> {selected.cwe_id}</div>}
                {selected.cvss_score && <div><span className="text-gray-400">CVSS:</span> {selected.cvss_score}</div>}
                {selected.tool_name && <div><span className="text-gray-400">Tool:</span> {selected.tool_name}</div>}
                {selected.confidence && <div><span className="text-gray-400">Confidence:</span> {selected.confidence}</div>}
                {selected.commit_author && <div><span className="text-gray-400">Author:</span> {selected.commit_author}</div>}
              </div>

              <div className="flex gap-2">
                <select value={selected.status} onChange={(e) => updateStatus(selected.id, e.target.value)} className="border rounded px-2 py-1 text-sm flex-1">
                  {['open', 'in_progress', 'fixed', 'false_positive'].map((s) => (
                    <option key={s} value={s}>{s.replace('_', ' ')}</option>
                  ))}
                </select>
                {!selected.jira_ticket_id && (
                  <button onClick={() => createJira(selected.id)} className="bg-blue-600 text-white px-3 py-1 rounded text-sm">Jira</button>
                )}
              </div>
              {selected.jira_ticket_url && (
                <a href={selected.jira_ticket_url} target="_blank" rel="noopener noreferrer" className="text-blue-600 text-xs hover:underline mt-2 block">
                  View Jira ticket
                </a>
              )}
            </div>
          ) : (
            <div className="bg-gray-50 rounded-lg p-4 text-center text-gray-400 text-sm">
              Click a finding to see details
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
