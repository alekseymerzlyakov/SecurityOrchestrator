/**
 * Zustand store for scan state, updated via WebSocket.
 */
import { create } from 'zustand';

// Tool display metadata
export const TOOL_META = {
  semgrep:        { label: 'Semgrep',      icon: '🔍', desc: 'SAST — паттерны уязвимостей' },
  gitleaks:       { label: 'Gitleaks',     icon: '🔑', desc: 'Поиск секретов в git' },
  trivy:          { label: 'Trivy',        icon: '📦', desc: 'CVE в зависимостях' },
  npm_audit:      { label: 'npm audit',    icon: '📋', desc: 'Аудит npm-пакетов' },
  eslint_security:{ label: 'ESLint Sec',   icon: '⚡', desc: 'JS-специфичные уязвимости' },
  retirejs:       { label: 'RetireJS',     icon: '📚', desc: 'Устаревшие JS-библиотеки' },
  ai_analysis:    { label: 'AI Analysis',  icon: '🤖', desc: 'Глубокий анализ через AI' },
};

const emptyProgress = () => ({
  scanId: null,
  stepName: '',
  status: '',
  filesProcessed: 0,
  totalFiles: 0,
  tokensUsed: 0,
  costUsd: 0,
  findingsCount: 0,
  percent: 0,
  message: '',
});

export const useScanStore = create((set, get) => ({
  // Current scan progress
  activeScan: null,
  progress: emptyProgress(),
  liveFindings: [],
  isConnected: false,

  /**
   * Pipeline steps — populated from scan_started event.
   * Each entry: { name, status, findingsCount, error, startedAt, finishedAt, statusMessage, interimCount }
   */
  steps: [],

  // Actions
  setConnected: (connected) => set({ isConnected: connected }),

  updateProgress: (data) => {
    const prev = get();

    // Update the matching step's status based on incoming progress message
    const stepName = data.step_name;
    const stepStatus = data.status; // 'running' | 'completed' | 'failed' | 'skipped'

    let updatedSteps = prev.steps;
    if (stepName && updatedSteps.length > 0) {
      updatedSteps = updatedSteps.map((s) => {
        // If a NEW step just started running, auto-close any previously running step
        // (handles edge case where step_complete arrives after next scan_progress)
        if (stepStatus === 'running' && s.name !== stepName && s.status === 'running') {
          return { ...s, status: 'completed', finishedAt: Date.now(), statusMessage: null, interimCount: 0 };
        }

        if (s.name !== stepName) return s;

        // Only update if the status is more advanced
        const updated = { ...s };
        if (stepStatus === 'running' && s.status !== 'running') {
          updated.status = 'running';
          updated.startedAt = Date.now();
        } else if ((stepStatus === 'completed' || stepStatus === 'failed' || stepStatus === 'skipped') && s.status !== 'completed' && s.status !== 'failed') {
          updated.status = stepStatus;
          updated.finishedAt = Date.now();
          updated.statusMessage = null;
          updated.interimCount = 0;
        }
        return updated;
      });
    }

    set({
      steps: updatedSteps,
      progress: {
        scanId: data.scan_id,
        stepName: data.step_name,
        status: data.status,
        filesProcessed: data.files_processed,
        totalFiles: data.total_files,
        tokensUsed: data.tokens_used,
        costUsd: data.cost_usd,
        findingsCount: data.findings_count,
        percent: data.percent,
        message: data.message,
      },
    });
  },

  /** Called when a step completes — update its findings count */
  completeStep: (stepName, findingsCount, status = 'completed', error = null) => {
    set((state) => ({
      steps: state.steps.map((s) =>
        s.name === stepName
          ? {
              ...s,
              status,
              findingsCount: findingsCount ?? s.findingsCount,
              error,
              finishedAt: Date.now(),
              statusMessage: null,   // clear interim message — show badge instead
              interimCount: 0,
            }
          : s
      ),
    }));
  },

  /** Called when a step emits an intermediate status message (step_status WS event) */
  updateStepStatus: (stepName, message, interimCount) => {
    set((state) => ({
      steps: state.steps.map((s) =>
        s.name === stepName
          ? { ...s, statusMessage: message, interimCount: interimCount ?? s.interimCount }
          : s
      ),
    }));
  },

  /** Initialize steps list from scan_started event */
  initSteps: (stepNames) => {
    set({
      steps: stepNames.map((name) => ({
        name,
        status: 'pending',
        findingsCount: 0,
        error: null,
        startedAt: null,
        finishedAt: null,
        statusMessage: null,
        interimCount: 0,
      })),
    });
  },

  addFinding: (data) =>
    set((state) => ({
      liveFindings: [data.finding, ...state.liveFindings].slice(0, 100),
    })),

  scanComplete: (data) =>
    set((state) => ({
      activeScan: null,
      progress: { ...state.progress, status: 'completed' },
      // Mark any still-pending/running steps as completed
      steps: state.steps.map((s) =>
        s.status === 'pending' || s.status === 'running'
          ? { ...s, status: 'completed', finishedAt: Date.now() }
          : s
      ),
    })),

  setActiveScan: (scan) => set({ activeScan: scan, liveFindings: [], steps: [] }),

  clearProgress: () =>
    set({
      activeScan: null,
      progress: emptyProgress(),
      liveFindings: [],
      steps: [],
    }),
}));
