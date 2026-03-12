import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useScanStore } from '../store/scanStore';
import BranchSelector from '../components/BranchSelector';
import PipelineStep from '../components/PipelineStep';
import CostEstimator from '../components/CostEstimator';
import { InformationCircleIcon } from '@heroicons/react/24/outline';

const MODE_INFO = {
  hybrid: {
    label: 'Hybrid',
    badge: 'Рекомендуется',
    badgeColor: 'bg-green-100 text-green-700',
    summary: 'Инструменты + умный AI',
    how: 'Сначала запускаются SAST-инструменты (Semgrep, Gitleaks, Trivy и др.). После их завершения AI анализирует только "горячие зоны" — файлы где найдены проблемы, плюс соседние файлы в той же директории для контекста.',
    pros: [
      'Самый точный результат — AI видит конкретные проблемы и ищет их эксплойты',
      'Экономия токенов: AI не тратит бюджет на "чистые" файлы',
      'Глубокий анализ цепочек уязвимостей (как SAST-находка ведёт к реальной атаке)',
      'Так работают топовые инструменты: Snyk, Semgrep Pro, CodeQL, GitHub Advanced Security',
    ],
    cons: ['Медленнее tools_only', 'Требует настроенного AI провайдера'],
    example: 'Semgrep находит dangerouslySetInnerHTML в 12 файлах → AI анализирует только эти 12 файлов + их директории (~40 файлов), а не весь репозиторий из 1686 файлов.',
  },
  tools_only: {
    label: 'Tools Only',
    badge: 'Быстро / Бесплатно',
    badgeColor: 'bg-blue-100 text-blue-700',
    summary: 'Только статические анализаторы',
    how: 'Запускаются только SAST-инструменты: Semgrep, Gitleaks, Trivy, npm audit, ESLint Security, RetireJS. AI не используется.',
    pros: [
      'Быстро — весь репозиторий за 2-5 минут',
      'Бесплатно — нет расходов на AI токены',
      'Хорошо для CI/CD пайплайна и частых проверок',
      'Отлично ловит: секреты, CVE в зависимостях, типовые паттерны XSS/injection',
    ],
    cons: [
      'Много false positives — инструменты не понимают контекст',
      'Не видит логические уязвимости (неправильный контроль доступа, обходы)',
      'Не может оценить реальную эксплуатируемость',
    ],
    example: 'Semgrep пометит каждый eval() как уязвимость, даже если входные данные предварительно санированы — AI бы это понял.',
  },
  ai_only: {
    label: 'AI Only',
    badge: 'Глубокий анализ',
    badgeColor: 'bg-purple-100 text-purple-700',
    summary: 'Только AI, весь репозиторий',
    how: 'AI получает весь репозиторий по чанкам. Файлы приоритизируются: сначала Tier 1 (auth, crypto, upload, extension), потом Tier 2 (routes, forms, services). Tier 3 (тесты, стили) пропускаются.',
    pros: [
      'Самый глубокий анализ — понимает контекст и архитектуру',
      'Находит логические уязвимости которые инструменты пропускают',
      'Объясняет атаку и даёт конкретный код для исправления',
      'Не даёт false positives на санированный код',
    ],
    cons: [
      'Дорого — весь репозиторий может стоить $50-200+',
      'Медленно — анализ большого репо занимает часы',
      'Нет данных от инструментов для контекста',
    ],
    example: 'AI проходит по всем 1686 файлам чанками по ~120К токенов, выдаёт security-анализ с рекомендациями.',
  },
};

function ModeInfoPopover({ mode }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const info = MODE_INFO[mode];

  useEffect(() => {
    if (!open) return;
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const keyHandler = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', handler);
    document.addEventListener('keydown', keyHandler);
    return () => { document.removeEventListener('mousedown', handler); document.removeEventListener('keydown', keyHandler); };
  }, [open]);

  return (
    <span className="relative inline-flex items-center" ref={ref}>
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}
        className="ml-1 text-gray-400 hover:text-blue-500 focus:outline-none"
        title={`Как работает ${info.label}`}
      >
        <InformationCircleIcon className="h-4 w-4" />
      </button>
      {open && (
        <div className="absolute left-6 top-0 z-50 w-96 bg-white rounded-xl shadow-2xl border border-gray-200 animate-in" style={{ minWidth: 360 }}>
          <div className="bg-gradient-to-r from-blue-600 to-blue-700 rounded-t-xl px-4 py-3 flex items-center justify-between">
            <div>
              <span className="text-white font-semibold text-sm">{info.label}</span>
              <span className={`ml-2 text-xs px-2 py-0.5 rounded-full font-medium ${info.badgeColor}`}>{info.badge}</span>
            </div>
            <button onClick={() => setOpen(false)} className="text-blue-200 hover:text-white text-lg leading-none">&times;</button>
          </div>
          <div className="p-4 space-y-3 text-sm max-h-[420px] overflow-y-auto">
            <p className="font-medium text-gray-800">{info.summary}</p>

            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Как работает</p>
              <p className="text-gray-700 text-xs leading-relaxed">{info.how}</p>
            </div>

            <div>
              <p className="text-xs font-semibold text-green-600 uppercase tracking-wide mb-1">Плюсы</p>
              <ul className="space-y-0.5">
                {info.pros.map((p, i) => (
                  <li key={i} className="text-xs text-gray-700 flex gap-1.5"><span className="text-green-500 mt-0.5 shrink-0">✓</span>{p}</li>
                ))}
              </ul>
            </div>

            <div>
              <p className="text-xs font-semibold text-red-500 uppercase tracking-wide mb-1">Минусы</p>
              <ul className="space-y-0.5">
                {info.cons.map((c, i) => (
                  <li key={i} className="text-xs text-gray-700 flex gap-1.5"><span className="text-red-400 mt-0.5 shrink-0">✗</span>{c}</li>
                ))}
              </ul>
            </div>

            <div className="bg-gray-50 rounded-lg p-2.5 border border-gray-100">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Пример</p>
              <p className="text-xs text-gray-600 italic">{info.example}</p>
            </div>
          </div>
        </div>
      )}
    </span>
  );
}

const DEFAULT_STEPS = [
  { tool_name: 'semgrep', enabled: true },
  { tool_name: 'gitleaks', enabled: true },
  { tool_name: 'trivy', enabled: true },
  { tool_name: 'npm_audit', enabled: true },
  { tool_name: 'eslint_security', enabled: true },
  { tool_name: 'retirejs', enabled: true },
  { tool_name: 'ai_analysis', enabled: true },
];

export default function PipelineBuilder() {
  const navigate = useNavigate();
  const { setActiveScan } = useScanStore();
  const [projects, setProjects] = useState([]);
  const [models, setModels] = useState([]);
  const [prompts, setPrompts] = useState([]);
  const [projectId, setProjectId] = useState('');
  const [branches, setBranches] = useState([]); // array of selected branch names
  const [mode, setMode] = useState('hybrid');
  const [modelId, setModelId] = useState('');
  const [promptId, setPromptId] = useState('');
  const [steps, setSteps] = useState(DEFAULT_STEPS);
  const [estimate, setEstimate] = useState(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    api.getProjects().then(setProjects).catch(() => {});
    api.getModels().then(setModels).catch(() => {});
    api.getPrompts().then(setPrompts).catch(() => {});
  }, []);

  const toggleStep = (name) => {
    setSteps(steps.map((s) => (s.tool_name === name ? { ...s, enabled: !s.enabled } : s)));
  };

  const moveStep = (idx, dir) => {
    const newSteps = [...steps];
    const swapIdx = idx + dir;
    if (swapIdx < 0 || swapIdx >= newSteps.length) return;
    [newSteps[idx], newSteps[swapIdx]] = [newSteps[swapIdx], newSteps[idx]];
    setSteps(newSteps);
  };

  const effectiveSteps = () => {
    let filtered = steps.filter((s) => s.enabled);
    if (mode === 'tools_only') filtered = filtered.filter((s) => s.tool_name !== 'ai_analysis');
    if (mode === 'ai_only') filtered = [{ tool_name: 'ai_analysis', enabled: true }];
    return filtered;
  };

  const startScan = async () => {
    if (!projectId || branches.length === 0) { alert('Выберите проект и хотя бы одну ветку'); return; }
    setStarting(true);
    try {
      const pipeline = effectiveSteps().map((s) => {
        if (s.tool_name === 'ai_analysis') {
          return { tool: 'ai_analysis', config: { model_id: modelId ? Number(modelId) : null, prompt_id: promptId ? Number(promptId) : null } };
        }
        return s.tool_name;
      });

      // Launch one scan per selected branch (parallel)
      const scans = await api.startScans(
        { project_id: Number(projectId), mode, pipeline_json: JSON.stringify(pipeline) },
        branches
      );

      // Navigate to monitor — show the first scan, others run in background
      setActiveScan(scans[0]);
      navigate('/monitor');
    } catch (err) {
      alert(err.message);
    } finally {
      setStarting(false);
    }
  };

  const showAIOptions = mode !== 'tools_only';

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Scan Pipeline</h1>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Configuration */}
        <div className="lg:col-span-2 space-y-4">
          <div className="bg-white rounded-lg shadow p-4">
            <h2 className="font-semibold mb-3">Project & Branches</h2>
            <select value={projectId} onChange={(e) => { setProjectId(e.target.value); setBranches([]); }}
              className="border rounded px-3 py-2 text-sm w-full mb-3">
              <option value="">Select project...</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name} — {p.repo_path}</option>)}
            </select>
            <BranchSelector projectId={projectId} value={branches} onChange={setBranches} />
          </div>

          <div className="bg-white rounded-lg shadow p-4">
            <h2 className="font-semibold mb-3">Scan Mode</h2>
            <div className="flex gap-5">
              {['hybrid', 'tools_only', 'ai_only'].map((m) => (
                <label key={m} className="flex items-center gap-1.5 text-sm cursor-pointer">
                  <input type="radio" name="mode" value={m} checked={mode === m} onChange={() => setMode(m)} />
                  <span className={`font-medium ${mode === m ? 'text-blue-700' : 'text-gray-700'}`}>
                    {MODE_INFO[m].label}
                  </span>
                  <ModeInfoPopover mode={m} />
                </label>
              ))}
            </div>
            {/* Active mode description */}
            <div className="mt-3 flex items-center gap-2 text-xs text-gray-500 bg-gray-50 rounded-lg px-3 py-2">
              <span className={`px-2 py-0.5 rounded-full font-medium text-xs ${MODE_INFO[mode].badgeColor}`}>
                {MODE_INFO[mode].badge}
              </span>
              <span>{MODE_INFO[mode].summary} — {MODE_INFO[mode].how.split('.')[0]}.</span>
            </div>
          </div>

          {showAIOptions && (
            <div className="bg-white rounded-lg shadow p-4">
              <h2 className="font-semibold mb-3">AI Configuration</h2>
              <div className="space-y-2">
                <select value={modelId} onChange={(e) => setModelId(e.target.value)} className="border rounded px-3 py-2 text-sm w-full">
                  <option value="">Select AI Model...</option>
                  {models.map((m) => <option key={m.id} value={m.id}>{m.name} ({m.model_id})</option>)}
                </select>
                <select value={promptId} onChange={(e) => setPromptId(e.target.value)} className="border rounded px-3 py-2 text-sm w-full">
                  <option value="">Default Prompt</option>
                  {prompts.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.category})</option>)}
                </select>
              </div>
            </div>
          )}

          <div className="bg-white rounded-lg shadow p-4">
            <h2 className="font-semibold mb-3">Pipeline Steps</h2>
            <div className="space-y-2">
              {steps.map((step, idx) => (
                <div key={step.tool_name} className="flex items-center gap-2">
                  <div className="flex flex-col gap-0.5">
                    <button onClick={() => moveStep(idx, -1)} className="text-gray-400 hover:text-gray-600 text-xs leading-none">&uarr;</button>
                    <button onClick={() => moveStep(idx, 1)} className="text-gray-400 hover:text-gray-600 text-xs leading-none">&darr;</button>
                  </div>
                  <div className="flex-1">
                    <PipelineStep step={{ ...step, status: 'pending' }} onToggle={toggleStep} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          {estimate && <CostEstimator estimate={estimate} />}

          <div className="bg-white rounded-lg shadow p-4">
            <h2 className="font-semibold mb-3">Summary</h2>
            <div className="text-sm space-y-1 text-gray-700">
              <p>Steps: {effectiveSteps().length}</p>
              <p>Mode: <span className="capitalize">{mode.replace('_', ' ')}</span></p>
              {modelId && <p>Model: {models.find((m) => m.id === Number(modelId))?.name}</p>}
              {branches.length > 0 && (
                <div className="mt-2 pt-2 border-t border-gray-100">
                  <p className="font-medium text-gray-500 text-xs mb-1">
                    {branches.length > 1 ? `${branches.length} веток → ${branches.length} сканов` : '1 ветка → 1 скан'}
                  </p>
                  <ul className="space-y-0.5">
                    {branches.map((b) => (
                      <li key={b} className="text-xs text-gray-600 flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-blue-400 shrink-0" />
                        {b}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>

          <button
            onClick={startScan}
            disabled={starting || !projectId || branches.length === 0}
            className={`w-full py-3 rounded-lg text-white font-semibold text-lg ${
              starting || !projectId || branches.length === 0
                ? 'bg-gray-400 cursor-not-allowed'
                : 'bg-green-600 hover:bg-green-700'
            }`}
          >
            {starting
              ? 'Starting...'
              : branches.length > 1
                ? `Start ${branches.length} Scans`
                : 'Start Scan'}
          </button>
        </div>
      </div>
    </div>
  );
}
