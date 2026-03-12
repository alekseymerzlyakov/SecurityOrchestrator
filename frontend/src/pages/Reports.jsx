import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { formatDate, formatNumber, formatCost } from '../utils/formatters';

// Severity colors
const SEV_STYLE = {
  critical: 'bg-red-600 text-white',
  high:     'bg-orange-500 text-white',
  medium:   'bg-yellow-400 text-gray-900',
  low:      'bg-blue-500 text-white',
  info:     'bg-gray-400 text-white',
};

function SevBadge({ sev, count }) {
  if (!count) return null;
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold ${SEV_STYLE[sev] || 'bg-gray-200 text-gray-700'}`}>
      {count} {sev}
    </span>
  );
}

// ── Markdown renderer (simple, no deps) ─────────────────────────────────────
function Markdown({ text }) {
  if (!text) return null;

  const lines = text.split('\n');
  const elements = [];
  let key = 0;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    if (trimmed.startsWith('### ')) {
      elements.push(
        <h3 key={key++} className="text-base font-bold text-gray-800 mt-5 mb-2">
          {renderInline(trimmed.slice(4))}
        </h3>
      );
    } else if (trimmed.startsWith('## ')) {
      elements.push(
        <h2 key={key++} className="text-lg font-bold text-gray-900 mt-6 mb-2 border-b border-gray-200 pb-1">
          {renderInline(trimmed.slice(3))}
        </h2>
      );
    } else if (trimmed.startsWith('# ')) {
      elements.push(
        <h1 key={key++} className="text-xl font-bold text-gray-900 mt-4 mb-3">
          {renderInline(trimmed.slice(2))}
        </h1>
      );
    } else if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      elements.push(
        <li key={key++} className="ml-4 text-sm text-gray-700 list-disc mb-1">
          {renderInline(trimmed.slice(2))}
        </li>
      );
    } else if (/^\d+\.\s/.test(trimmed)) {
      const content = trimmed.replace(/^\d+\.\s/, '');
      elements.push(
        <li key={key++} className="ml-4 text-sm text-gray-700 list-decimal mb-1">
          {renderInline(content)}
        </li>
      );
    } else if (trimmed === '') {
      elements.push(<div key={key++} className="h-1" />);
    } else if (trimmed.startsWith('---')) {
      elements.push(<hr key={key++} className="border-gray-200 my-4" />);
    } else {
      elements.push(
        <p key={key++} className="text-sm text-gray-700 mb-1 leading-relaxed">
          {renderInline(trimmed)}
        </p>
      );
    }
  }
  return <div className="prose-like">{elements}</div>;
}

function renderInline(text) {
  // Bold **text**, inline code `code`, emoji stays as-is
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} className="font-semibold text-gray-900">{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={i} className="bg-gray-100 px-1 py-0.5 rounded text-xs font-mono text-gray-800">{part.slice(1, -1)}</code>;
    }
    return part;
  });
}

// ── AI Summary Panel ─────────────────────────────────────────────────────────
function SummaryPanel({ scanId, onClose }) {
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);

  const loadSummary = (regenerate = false) => {
    if (regenerate) setRegenerating(true);
    else setLoading(true);
    setError(null);
    api.summarizeReport(scanId, regenerate)
      .then((data) => setSummary(data))
      .catch((e) => setError(e.message))
      .finally(() => { setLoading(false); setRegenerating(false); });
  };

  useEffect(() => { loadSummary(false); }, [scanId]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gradient-to-r from-blue-700 to-blue-600 rounded-t-xl">
          <div>
            <h2 className="text-white font-bold text-lg">🤖 AI Executive Summary</h2>
            {summary && (
              <p className="text-blue-200 text-xs mt-0.5">
                {summary.cached
                  ? `📦 Кэш от ${new Date(summary.generated_at).toLocaleString()}`
                  : `${summary.model_used} · ${summary.prompt_name}`}
              </p>
            )}
          </div>
          <button onClick={onClose} className="text-blue-200 hover:text-white text-2xl leading-none font-light">
            &times;
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {loading && (
            <div className="flex items-center gap-3 text-gray-500 py-8 justify-center">
              <span className="animate-spin text-2xl">⏳</span>
              <span>AI анализирует отчёт...</span>
            </div>
          )}
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 text-sm space-y-2">
              <p><strong>Ошибка:</strong> {error}</p>
              {error.includes('кредит') || error.includes('баланс') || error.includes('billing') || error.includes('credit') ? (
                <p className="text-xs text-red-500">
                  Пополните баланс на{' '}
                  <a href="https://console.anthropic.com/settings/billing" target="_blank" rel="noreferrer"
                     className="underline font-medium">console.anthropic.com → Billing</a>
                </p>
              ) : error.includes('Rate limit') || error.includes('429') ? (
                <p className="text-xs text-red-500">
                  Подождите 1–2 минуты и попробуйте снова. Или переключитесь на <strong>claude-haiku</strong> в Settings → AI Models.
                </p>
              ) : error.includes('API') || error.includes('ключ') || error.includes('auth') ? (
                <p className="text-xs text-red-500">Проверьте API ключ в <strong>Settings → AI Providers</strong></p>
              ) : (
                <p className="text-xs text-red-500">Проверьте настройки провайдера в <strong>Settings</strong></p>
              )}
            </div>
          )}
          {summary && <Markdown text={summary.summary} />}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-gray-100 flex justify-between items-center gap-3">
          <div className="text-xs text-gray-400">
            {summary?.cached && '📦 Из кэша · '}
            {summary && new Date(summary.generated_at).toLocaleString()}
          </div>
          <div className="flex gap-2 ml-auto">
            {summary && (
              <button
                onClick={() => loadSummary(true)}
                disabled={regenerating}
                className="bg-blue-50 text-blue-600 border border-blue-200 px-3 py-1.5 rounded text-xs hover:bg-blue-100 disabled:opacity-50"
              >
                {regenerating ? '⏳ Генерация...' : '🔄 Обновить'}
              </button>
            )}
            <button onClick={onClose} className="bg-gray-100 text-gray-700 px-4 py-2 rounded hover:bg-gray-200 text-sm">
              Закрыть
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Report viewer (inline HTML in iframe) ────────────────────────────────────
function ReportViewer({ scanId, reportType, onClose }) {
  const url = api.viewReportUrl(scanId, reportType);

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-gray-900">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 py-2 bg-gray-800 border-b border-gray-700">
        <span className="text-white font-medium text-sm">
          📄 Scan #{scanId} — {reportType === 'technical' ? 'Technical' : 'Executive'} Report
        </span>
        <div className="ml-auto flex gap-2">
          <a
            href={api.downloadReport(scanId, 'html', reportType)}
            className="text-xs bg-blue-600 text-white px-3 py-1.5 rounded hover:bg-blue-700"
            download
          >
            ⬇ HTML
          </a>
          <a
            href={api.downloadReport(scanId, 'json', reportType)}
            className="text-xs bg-gray-600 text-white px-3 py-1.5 rounded hover:bg-gray-500"
            download
          >
            ⬇ JSON
          </a>
          <button
            onClick={onClose}
            className="text-xs bg-red-700 text-white px-3 py-1.5 rounded hover:bg-red-600"
          >
            ✕ Закрыть
          </button>
        </div>
      </div>

      {/* iframe */}
      <iframe
        src={url}
        title={`Report for scan ${scanId}`}
        className="flex-1 bg-white"
        sandbox="allow-same-origin allow-scripts"
      />
    </div>
  );
}

// ── Scan card ────────────────────────────────────────────────────────────────
function ScanCard({ scan, onView, onSummary }) {
  const [generating, setGenerating] = useState(null);

  const duration = scan.started_at && scan.finished_at
    ? Math.round((new Date(scan.finished_at) - new Date(scan.started_at)) / 1000)
    : null;
  const durationStr = duration
    ? duration < 60 ? `${duration}s` : `${Math.floor(duration / 60)}m ${duration % 60}s`
    : null;

  const downloadHtml = async (reportType) => {
    const key = `${scan.id}-html-${reportType}`;
    setGenerating(key);
    try {
      // First generate the file server-side
      await api.generateReport(scan.id, { format: 'html', report_type: reportType });
      // Then download
      window.open(api.downloadReport(scan.id, 'html', reportType), '_blank');
    } catch (e) {
      alert(e.message);
    } finally {
      setGenerating(null);
    }
  };

  const downloadPdf = async (reportType) => {
    const key = `${scan.id}-pdf-${reportType}`;
    setGenerating(key);
    try {
      await api.generateReport(scan.id, { format: 'pdf', report_type: reportType });
      window.open(api.downloadReport(scan.id, 'pdf', reportType), '_blank');
    } catch (e) {
      alert(e.message);
    } finally {
      setGenerating(null);
    }
  };

  const downloadJson = async (reportType) => {
    window.open(api.downloadReport(scan.id, 'json', reportType), '_blank');
  };

  return (
    <div className="bg-white rounded-xl shadow border border-gray-100 overflow-hidden">
      {/* Header bar */}
      <div className="flex items-center gap-3 px-5 py-3 bg-gray-50 border-b border-gray-100">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-gray-800">Scan #{scan.id}</span>
            <span className="font-mono text-sm text-blue-600 bg-blue-50 px-2 py-0.5 rounded">
              {scan.branch}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
              scan.status === 'completed' ? 'bg-green-100 text-green-700' :
              scan.status === 'stopped'   ? 'bg-yellow-100 text-yellow-700' :
              scan.status === 'failed'    ? 'bg-red-100 text-red-700' :
              'bg-gray-100 text-gray-600'
            }`}>
              {scan.status}
            </span>
            <span className="text-xs text-gray-400 capitalize">{scan.mode?.replace('_', ' ')}</span>
          </div>
          <div className="flex items-center gap-3 mt-1 text-xs text-gray-400 flex-wrap">
            {scan.project_name && <span>📁 {scan.project_name}</span>}
            <span>{formatDate(scan.started_at)}</span>
            {durationStr && <span>⏱ {durationStr}</span>}
            {scan.tokens_used > 0 && <span>🔤 {formatNumber(scan.tokens_used)} tokens</span>}
            {scan.cost_usd > 0 && <span>💰 {formatCost(scan.cost_usd)}</span>}
          </div>
        </div>

        {/* AI Summary button */}
        <button
          onClick={() => onSummary(scan.id)}
          className="flex-shrink-0 flex items-center gap-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm px-3 py-2 rounded-lg font-medium transition-colors"
          title="Получить AI executive summary"
        >
          🤖 Summary
        </button>
      </div>

      {/* Findings severity row */}
      {scan.findings_count > 0 && (
        <div className="px-5 py-2.5 border-b border-gray-100 flex items-center gap-2 flex-wrap">
          <span className="text-xs text-gray-500 font-medium mr-1">Findings:</span>
          <SevBadge sev="critical" count={scan.critical_count} />
          <SevBadge sev="high" count={scan.high_count} />
          <span className="text-xs text-gray-400 ml-1">
            {scan.findings_count} total
          </span>
        </div>
      )}
      {scan.findings_count === 0 && scan.status === 'completed' && (
        <div className="px-5 py-2 border-b border-gray-100">
          <span className="text-xs text-green-600 font-medium">✓ No findings — clean scan</span>
        </div>
      )}

      {/* Report actions */}
      <div className="px-5 py-3 flex items-center gap-4 flex-wrap">
        {/* View online */}
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-400 font-medium">Просмотр:</span>
          <button
            onClick={() => onView(scan.id, 'technical')}
            className="text-xs bg-indigo-50 text-indigo-700 hover:bg-indigo-100 px-3 py-1.5 rounded font-medium"
          >
            📄 Technical
          </button>
          <button
            onClick={() => onView(scan.id, 'executive')}
            className="text-xs bg-purple-50 text-purple-700 hover:bg-purple-100 px-3 py-1.5 rounded font-medium"
          >
            📊 Executive
          </button>
        </div>

        <div className="w-px h-6 bg-gray-200" />

        {/* Download */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs text-gray-400 font-medium">Скачать:</span>
          <button
            onClick={() => downloadHtml('technical')}
            disabled={!!generating}
            className="text-xs bg-gray-50 text-gray-600 hover:bg-gray-100 px-2.5 py-1.5 rounded disabled:opacity-50"
          >
            {generating === `${scan.id}-html-technical` ? '...' : 'HTML Tech'}
          </button>
          <button
            onClick={() => downloadHtml('executive')}
            disabled={!!generating}
            className="text-xs bg-gray-50 text-gray-600 hover:bg-gray-100 px-2.5 py-1.5 rounded disabled:opacity-50"
          >
            {generating === `${scan.id}-html-executive` ? '...' : 'HTML Exec'}
          </button>
          <button
            onClick={() => downloadJson('technical')}
            className="text-xs bg-gray-50 text-gray-600 hover:bg-gray-100 px-2.5 py-1.5 rounded"
          >
            JSON
          </button>
          <button
            onClick={() => downloadPdf('technical')}
            disabled={!!generating}
            className="text-xs bg-gray-50 text-gray-600 hover:bg-gray-100 px-2.5 py-1.5 rounded disabled:opacity-50"
          >
            {generating?.startsWith(`${scan.id}-pdf`) ? '...' : 'PDF'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main page ────────────────────────────────────────────────────────────────
export default function Reports() {
  const [scans, setScans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [viewer, setViewer] = useState(null);   // { scanId, reportType }
  const [summary, setSummary] = useState(null); // { scanId }

  useEffect(() => {
    api.getScanHistory()
      .then((data) => setScans(Array.isArray(data) ? data : []))
      .catch(() => setScans([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-gray-400 py-10 text-center">Loading...</div>;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Reports</h1>
        <p className="text-sm text-gray-400">
          {scans.length} {scans.length === 1 ? 'scan' : 'scans'} в истории
        </p>
      </div>

      {scans.length === 0 ? (
        <div className="text-center py-20 text-gray-400">
          <p className="text-4xl mb-3">📭</p>
          <p className="text-lg font-medium mb-1">Нет сканов</p>
          <p className="text-sm">Запустите скан в Pipeline Builder чтобы получить отчёт</p>
        </div>
      ) : (
        <div className="space-y-4">
          {scans.map((scan) => (
            <ScanCard
              key={scan.id}
              scan={scan}
              onView={(scanId, reportType) => setViewer({ scanId, reportType })}
              onSummary={(scanId) => setSummary({ scanId })}
            />
          ))}
        </div>
      )}

      {/* Inline HTML report viewer */}
      {viewer && (
        <ReportViewer
          scanId={viewer.scanId}
          reportType={viewer.reportType}
          onClose={() => setViewer(null)}
        />
      )}

      {/* AI Summary modal */}
      {summary && (
        <SummaryPanel
          scanId={summary.scanId}
          onClose={() => setSummary(null)}
        />
      )}
    </div>
  );
}
