import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useScanStore, TOOL_META } from '../store/scanStore';
import { api } from '../api/client';
import ProgressBar from '../components/ProgressBar';
import FindingCard from '../components/FindingCard';
import { formatNumber, formatCost } from '../utils/formatters';

// ── Step status icon ─────────────────────────────────────────────────────────
function StepStatusIcon({ status }) {
  if (status === 'completed') return <span className="text-green-500 text-base leading-none">✓</span>;
  if (status === 'failed')    return <span className="text-red-500 text-base leading-none">✗</span>;
  if (status === 'skipped')   return <span className="text-gray-400 text-base leading-none">–</span>;
  if (status === 'running')   return (
    <span className="relative flex h-4 w-4">
      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
      <span className="relative inline-flex rounded-full h-4 w-4 bg-blue-500" />
    </span>
  );
  return <span className="h-4 w-4 rounded-full border-2 border-gray-300 inline-block" />;
}

function stepRowBg(status) {
  if (status === 'running')   return 'bg-blue-50 border-blue-200';
  if (status === 'completed') return 'bg-green-50 border-green-100';
  if (status === 'failed')    return 'bg-red-50 border-red-200';
  if (status === 'skipped')   return 'bg-gray-50 border-gray-200';
  return 'bg-white border-gray-100';
}

function durationStr(startedAt, finishedAt) {
  if (!startedAt) return null;
  const secs = Math.round(((finishedAt ?? Date.now()) - startedAt) / 1000);
  if (secs < 60) return `${secs}s`;
  return `${Math.floor(secs / 60)}m ${secs % 60}s`;
}

// ── Pipeline Steps panel ─────────────────────────────────────────────────────
function PipelineStepsPanel({ steps }) {
  if (!steps || steps.length === 0) return null;

  const doneCount = steps.filter((s) => s.status === 'completed' || s.status === 'failed').length;

  return (
    <div className="bg-white rounded-lg shadow p-4 mb-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold text-gray-700 text-sm uppercase tracking-wide">
          Pipeline Steps
        </h2>
        <span className="text-xs text-gray-400">{doneCount} / {steps.length} завершено</span>
      </div>
      <div className="space-y-1">
        {steps.map((step) => {
          const meta = TOOL_META[step.name] || { label: step.name, icon: '🔧', desc: '' };
          const dur = durationStr(step.startedAt, step.finishedAt);

          return (
            <div
              key={step.name}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg border transition-colors ${stepRowBg(step.status)}`}
            >
              {/* Animated status dot */}
              <div className="flex-shrink-0 w-5 flex items-center justify-center">
                <StepStatusIcon status={step.status} />
              </div>

              {/* Tool emoji */}
              <span className="text-base leading-none flex-shrink-0 select-none">{meta.icon}</span>

              {/* Tool name + status */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`text-sm font-medium ${
                    step.status === 'running'   ? 'text-blue-700' :
                    step.status === 'completed' ? 'text-gray-800' :
                    step.status === 'failed'    ? 'text-red-700'  :
                    'text-gray-400'
                  }`}>
                    {meta.label}
                  </span>

                  {step.status === 'running' && !step.statusMessage && (
                    <span className="text-xs text-blue-400 animate-pulse">работает...</span>
                  )}
                  {step.status === 'pending' && (
                    <span className="text-xs text-gray-300">в очереди</span>
                  )}
                  {step.status === 'skipped' && (
                    <span className="text-xs text-gray-400">пропущен</span>
                  )}
                  {/* Live interim findings count badge while running */}
                  {step.status === 'running' && step.interimCount > 0 && (
                    <span className="text-xs px-1.5 py-0.5 rounded-full bg-orange-100 text-orange-700 font-medium animate-pulse">
                      {step.interimCount} найдено
                    </span>
                  )}
                </div>

                {/* Live status message line — only while actually running */}
                {step.status === 'running' && step.statusMessage && (
                  <p className="text-xs text-blue-500 mt-0.5 truncate" title={step.statusMessage}>
                    <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse mr-1 align-middle" />
                    {step.statusMessage}
                  </p>
                )}
                {/* Next-in-queue hint */}
                {step.status === 'pending' && steps.findIndex((s) => s.status === 'running') !== -1 && (
                  <p className="text-xs text-gray-300 mt-0.5">следующий</p>
                )}
                {step.error && (
                  <p className="text-xs text-red-500 truncate mt-0.5" title={step.error}>
                    {step.error}
                  </p>
                )}
              </div>

              {/* Duration */}
              {dur && (
                <span className="text-xs text-gray-400 flex-shrink-0 font-mono">{dur}</span>
              )}

              {/* Findings badge */}
              {(step.status === 'completed' || step.status === 'failed') && (
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium flex-shrink-0 ${
                  step.findingsCount > 0
                    ? 'bg-red-100 text-red-700'
                    : 'bg-gray-100 text-gray-500'
                }`}>
                  {step.findingsCount > 0 ? `${step.findingsCount} findings` : 'clean'}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Main page ────────────────────────────────────────────────────────────────
export default function LiveMonitor() {
  const { progress, liveFindings, activeScan, steps, initSteps, completeStep } = useScanStore();
  const [stopping, setStopping] = useState(false);
  const [startTime] = useState(Date.now());

  // If steps are empty (user navigated away and came back), load from API
  const scanId = progress.scanId || activeScan?.id;
  useEffect(() => {
    if (!scanId || steps.length > 0) return;
    api.getScanSteps(scanId).then((apiSteps) => {
      if (!apiSteps || apiSteps.length === 0) return;
      initSteps(apiSteps.map((s) => s.tool_name));
      apiSteps.forEach((s) => {
        if (s.status === 'completed' || s.status === 'failed' || s.status === 'skipped') {
          completeStep(s.tool_name, s.findings_count, s.status, s.error_message);
        }
      });
    }).catch(() => {});
  }, [scanId]);

  const isRunning = progress.status === 'running' || progress.status === 'budget_exceeded';
  const currentMeta = progress.stepName
    ? (TOOL_META[progress.stepName] || { label: progress.stepName, icon: '🔧', desc: '' })
    : null;

  const handleStop = async () => {
    if (!progress.scanId) return;
    setStopping(true);
    try { await api.stopScan(progress.scanId); } catch { /* ignore */ }
    finally { setStopping(false); }
  };

  // ETA
  const elapsed = (Date.now() - startTime) / 1000;
  const eta = progress.percent > 0
    ? Math.round((elapsed / progress.percent) * (100 - progress.percent))
    : null;
  const etaStr = eta ? `${Math.floor(eta / 60)}m ${eta % 60}s` : '--';

  if (!progress.scanId && !activeScan) {
    return (
      <div className="text-center py-20">
        <h1 className="text-2xl font-bold mb-4">Live Monitor</h1>
        <p className="text-gray-500 mb-4">No scan is currently running.</p>
        <Link to="/pipeline" className="text-blue-600 hover:underline">
          Go to Pipeline Builder to start a scan
        </Link>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="flex justify-between items-start mb-4">
        <div>
          <h1 className="text-2xl font-bold">Live Monitor</h1>
          {currentMeta && isRunning && (
            <p className="text-sm text-gray-500 mt-0.5">
              {currentMeta.icon}{' '}
              <span className="font-medium text-blue-600">{currentMeta.label}</span>
              {currentMeta.desc && (
                <span className="text-gray-400"> — {currentMeta.desc}</span>
              )}
            </p>
          )}
          {!isRunning && progress.status === 'completed' && (
            <p className="text-sm text-green-600 mt-0.5">✓ Все инструменты завершили работу</p>
          )}
        </div>
        {isRunning && (
          <button
            onClick={handleStop}
            disabled={stopping}
            className="bg-red-600 text-white px-4 py-2 rounded hover:bg-red-700 text-sm flex-shrink-0"
          >
            {stopping ? 'Stopping...' : 'Stop Scan'}
          </button>
        )}
      </div>

      {/* Status banners */}
      {progress.status === 'budget_exceeded' && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-4">
          <p className="text-yellow-800 font-medium">Budget exceeded — scan stopped automatically.</p>
          <p className="text-yellow-600 text-sm">{progress.message}</p>
        </div>
      )}
      {progress.status === 'completed' && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">
          <p className="text-green-800 font-medium">✓ Scan completed successfully!</p>
          {steps.length > 0 && (
            <p className="text-green-600 text-sm mt-1">
              {steps.filter((s) => s.findingsCount > 0).length} из {steps.length} инструментов нашли проблемы
              {' · '}
              {steps.reduce((acc, s) => acc + (s.findingsCount || 0), 0)} total findings
            </p>
          )}
        </div>
      )}

      {/* Overall progress bar */}
      <div className="bg-white rounded-lg shadow p-4 mb-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-gray-600">
            {isRunning && currentMeta
              ? <>{currentMeta.icon} <span className="text-blue-700 font-semibold">{currentMeta.label}</span>{' '}<span className="text-gray-400">— {progress.message}</span></>
              : <span className="text-gray-500">{progress.message || (progress.status === 'completed' ? 'Завершено' : 'Ожидание...')}</span>
            }
          </span>
          <span className="text-sm font-mono text-gray-400">{Math.round(progress.percent || 0)}%</span>
        </div>
        <ProgressBar
          percent={progress.percent}
          label="Overall Progress"
          color={isRunning ? 'bg-blue-500' : 'bg-green-500'}
        />
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
        <div className="bg-white rounded-lg shadow p-3 text-center">
          <p className="text-xs text-gray-500 mb-1">Steps</p>
          <p className="text-xl font-bold text-gray-800">
            {steps.filter((s) => s.status === 'completed' || s.status === 'failed').length}
            <span className="text-sm text-gray-400"> / {steps.length || '?'}</span>
          </p>
        </div>
        <div className="bg-white rounded-lg shadow p-3 text-center">
          <p className="text-xs text-gray-500 mb-1">Files</p>
          <p className="text-xl font-bold text-gray-800">
            {progress.filesProcessed || 0}
            {progress.totalFiles ? <span className="text-sm text-gray-400"> / {progress.totalFiles}</span> : ''}
          </p>
        </div>
        <div className="bg-white rounded-lg shadow p-3 text-center">
          <p className="text-xs text-gray-500 mb-1">Tokens</p>
          <p className="text-xl font-bold font-mono text-gray-800">{formatNumber(progress.tokensUsed)}</p>
        </div>
        <div className="bg-white rounded-lg shadow p-3 text-center">
          <p className="text-xs text-gray-500 mb-1">Findings</p>
          <p className="text-xl font-bold text-red-600">{progress.findingsCount}</p>
        </div>
        <div className="bg-white rounded-lg shadow p-3 text-center">
          <p className="text-xs text-gray-500 mb-1">ETA</p>
          <p className="text-xl font-bold text-gray-800">{etaStr}</p>
        </div>
      </div>

      {/* ★ Pipeline steps — the main new section */}
      <PipelineStepsPanel steps={steps} />

      {/* Live findings */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-3">
          Live Findings
          {liveFindings.length > 0 && (
            <span className="ml-2 text-sm font-normal text-red-600">({liveFindings.length})</span>
          )}
        </h2>
        <div className="space-y-2 max-h-96 overflow-auto">
          {liveFindings.length > 0 ? (
            liveFindings.map((f, i) => <FindingCard key={i} finding={{ ...f, status: 'open' }} />)
          ) : (
            <p className="text-gray-400 text-sm">Waiting for findings...</p>
          )}
        </div>
      </div>
    </div>
  );
}
