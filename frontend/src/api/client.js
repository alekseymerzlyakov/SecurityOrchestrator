/**
 * API client for AISO backend.
 */

const BASE_URL = '/api';

async function request(path, options = {}) {
  const url = `${BASE_URL}${path}`;
  const config = {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  };

  if (config.body && typeof config.body === 'object') {
    config.body = JSON.stringify(config.body);
  }

  const response = await fetch(url, config);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  if (response.status === 204) return null;
  return response.json();
}

export const api = {
  // Health
  health: () => request('/health'),

  // Projects
  getProjects: () => request('/projects'),
  createProject: (data) => request('/projects', { method: 'POST', body: data }),
  getProject: (id) => request(`/projects/${id}`),
  deleteProject: (id) => request(`/projects/${id}`, { method: 'DELETE' }),
  getBranches: (id) => request(`/projects/${id}/branches`),
  getAuthors: (id) => request(`/projects/${id}/authors`),

  // Scans
  getScans: (projectId) => request(`/scans${projectId ? `?project_id=${projectId}` : ''}`),
  startScan: (data) => request('/scans', { method: 'POST', body: data }),
  /** Start one scan per branch in parallel. Returns array of scan objects. */
  startScans: (baseData, branches) =>
    Promise.all(branches.map((branch) => request('/scans', { method: 'POST', body: { ...baseData, branch } }))),
  getScan: (id) => request(`/scans/${id}`),
  getScanProgress: (id) => request(`/scans/${id}/progress`),
  stopScan: (id) => request(`/scans/${id}/stop`, { method: 'POST' }),
  getScanSteps: (id) => request(`/scans/${id}/steps`),

  // Findings
  getFindings: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/findings${query ? `?${query}` : ''}`);
  },
  getFinding: (id) => request(`/findings/${id}`),
  updateFindingStatus: (id, status) =>
    request(`/findings/${id}/status`, { method: 'PATCH', body: { status } }),
  getFindingsSummary: () => request('/findings/summary'),
  getFindingsByScan: (scanId) => request(`/findings/by-scan/${scanId}`),

  // Settings - Providers
  getProviders: () => request('/settings/providers'),
  createProvider: (data) => request('/settings/providers', { method: 'POST', body: data }),
  updateProvider: (id, data) => request(`/settings/providers/${id}`, { method: 'PUT', body: data }),
  deleteProvider: (id) => request(`/settings/providers/${id}`, { method: 'DELETE' }),

  // Settings - Models
  getModels: () => request('/settings/models'),
  createModel: (data) => request('/settings/models', { method: 'POST', body: data }),
  updateModel: (id, data) => request(`/settings/models/${id}`, { method: 'PUT', body: data }),
  deleteModel: (id) => request(`/settings/models/${id}`, { method: 'DELETE' }),

  // Settings - Tools
  getTools: () => request('/settings/tools'),
  updateTool: (id, data) => request(`/settings/tools/${id}`, { method: 'PUT', body: data }),
  checkTool: (name) => request(`/settings/tools/${name}/check`),

  // Prompts
  getPrompts: (category) => request(`/prompts${category ? `?category=${category}` : ''}`),
  createPrompt: (data) => request('/prompts', { method: 'POST', body: data }),
  getPrompt: (id) => request(`/prompts/${id}`),
  updatePrompt: (id, data) => request(`/prompts/${id}`, { method: 'PUT', body: data }),
  deletePrompt: (id) => request(`/prompts/${id}`, { method: 'DELETE' }),
  setDefaultPrompt: (id) => request(`/prompts/${id}/set-default`, { method: 'POST' }),

  // Reports
  getScanHistory: () => request('/reports/scans'),
  generateReport: (scanId, data) =>
    request(`/reports/${scanId}/generate`, { method: 'POST', body: data }),
  downloadReport: (scanId, format, reportType = 'technical') =>
    `${BASE_URL}/reports/${scanId}/download/${format}?report_type=${reportType}`,
  viewReportUrl: (scanId, reportType = 'technical') =>
    `${BASE_URL}/reports/${scanId}/view?report_type=${reportType}`,
  summarizeReport: (scanId, regenerate = false) =>
    request(`/reports/${scanId}/summarize${regenerate ? '?regenerate=true' : ''}`, { method: 'POST' }),

  // Jira
  getJiraConfig: () => request('/jira/config'),
  saveJiraConfig: (data) => request('/jira/config', { method: 'POST', body: data }),
  updateJiraConfig: (id, data) => request(`/jira/config/${id}`, { method: 'PUT', body: data }),
  testJiraConnection: () => request('/jira/test-connection', { method: 'POST' }),
  createJiraTicket: (findingId) =>
    request(`/jira/create-ticket/${findingId}`, { method: 'POST' }),
};
