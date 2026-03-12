import { useState, useEffect } from 'react';
import { api } from '../api/client';
import SeverityBadge from '../components/SeverityBadge';
import { formatNumber, formatCost, formatDate } from '../utils/formatters';

const SCORE_COLOR = (s) => (s >= 80 ? 'text-green-500' : s >= 50 ? 'text-yellow-500' : 'text-red-500');

export default function Dashboard() {
  const [summary, setSummary] = useState(null);
  const [scans, setScans] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.getFindingsSummary().catch(() => null),
      api.getScans().catch(() => []),
    ]).then(([s, sc]) => {
      setSummary(s);
      setScans(Array.isArray(sc) ? sc : []);
      setLoading(false);
    });
  }, []);

  if (loading) return <div className="text-gray-400">Loading dashboard...</div>;

  const lastScan = scans[0];
  // Calculate security score: start at 100, deduct by severity
  const total = summary?.total ?? 0;
  const critCount = summary?.critical ?? 0;
  const highCount = summary?.high ?? 0;
  const medCount = summary?.medium ?? 0;
  const lowCount = summary?.low ?? 0;
  const score = total > 0
    ? Math.max(0, Math.round(100 - (critCount * 15 + highCount * 8 + medCount * 3 + lowCount * 1)))
    : 100;
  const counts = {
    critical: critCount,
    high: highCount,
    medium: medCount,
    low: lowCount,
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>

      <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-6">
        {/* Security Score */}
        <div className="bg-white rounded-lg shadow p-6 text-center">
          <p className="text-sm text-gray-500 mb-1">Security Score</p>
          <p className={`text-5xl font-bold ${SCORE_COLOR(score)}`}>{score}</p>
          <p className="text-xs text-gray-400 mt-1">/ 100</p>
        </div>

        {/* Severity cards */}
        {['critical', 'high', 'medium', 'low'].map((sev) => (
          <div key={sev} className="bg-white rounded-lg shadow p-4">
            <div className="flex items-center justify-between mb-2">
              <SeverityBadge severity={sev} />
              <span className="text-2xl font-bold">{counts[sev] || 0}</span>
            </div>
            <p className="text-xs text-gray-400 capitalize">{sev} findings</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Last Scan */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold mb-3">Last Scan</h2>
          {lastScan ? (
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">Date</span>
                <span>{formatDate(lastScan.started_at)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Branch</span>
                <span className="font-mono">{lastScan.branch}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Status</span>
                <span className={lastScan.status === 'completed' ? 'text-green-600' : 'text-yellow-600'}>
                  {lastScan.status}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Mode</span>
                <span>{lastScan.mode}</span>
              </div>
            </div>
          ) : (
            <p className="text-gray-400">No scans yet</p>
          )}
        </div>

        {/* Token Usage */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold mb-3">Token Usage (Latest Scan)</h2>
          {lastScan ? (
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">Tokens Used</span>
                <span className="font-mono">{formatNumber(lastScan.tokens_used || 0)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Cost</span>
                <span className="font-mono">{formatCost(lastScan.cost_usd || 0)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Est. Total Cost</span>
                <span className="font-mono">{formatCost(lastScan.estimated_total_cost || 0)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Files Processed</span>
                <span>{lastScan.files_processed || 0} / {lastScan.total_files || '?'}</span>
              </div>
            </div>
          ) : (
            <p className="text-gray-400">No data yet</p>
          )}
        </div>
      </div>
    </div>
  );
}
