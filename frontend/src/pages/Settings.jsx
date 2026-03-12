import { useState, useEffect } from 'react';
import { api } from '../api/client';
import ToolInfoPopover from '../components/ToolInfoPopover';

function Section({ title, children }) {
  return (
    <div className="bg-white rounded-lg shadow p-6 mb-6">
      <h2 className="text-lg font-semibold mb-4">{title}</h2>
      {children}
    </div>
  );
}

export default function Settings() {
  const [tab, setTab] = useState('providers');
  const [providers, setProviders] = useState([]);
  const [models, setModels] = useState([]);
  const [tools, setTools] = useState([]);
  const [jiraConfig, setJiraConfig] = useState(null);
  const [providerForm, setProviderForm] = useState({ name: '', provider_type: 'anthropic', api_key: '', base_url: '' });
  const [modelForm, setModelForm] = useState({ provider_id: '', name: '', model_id: '', context_window: 200000, max_tokens_per_run: 1000000, max_budget_usd: 50, input_price_per_mtok: 15, output_price_per_mtok: 75, requests_per_minute: '' });
  const [jiraForm, setJiraForm] = useState({ base_url: '', user_email: '', api_token: '', project_key: '', issue_type: 'Bug' });
  const [showProviderForm, setShowProviderForm] = useState(false);
  const [showModelForm, setShowModelForm] = useState(false);
  const [jiraTestResult, setJiraTestResult] = useState(null);
  const [editingProvider, setEditingProvider] = useState(null);
  const [editProviderForm, setEditProviderForm] = useState({ name: '', provider_type: 'anthropic', api_key: '', base_url: '' });
  const [editingModel, setEditingModel] = useState(null);
  const [editModelForm, setEditModelForm] = useState({ provider_id: '', name: '', model_id: '', context_window: 200000, max_tokens_per_run: 1000000, max_budget_usd: 50, input_price_per_mtok: 15, output_price_per_mtok: 75, requests_per_minute: '' });

  useEffect(() => {
    api.getProviders().then(setProviders).catch(() => {});
    api.getModels().then(setModels).catch(() => {});
    api.getTools().then(setTools).catch(() => {});
    api.getJiraConfig().then((c) => { setJiraConfig(c); if (c) setJiraForm(c); }).catch(() => {});
  }, []);

  const saveProvider = async (e) => {
    e.preventDefault();
    await api.createProvider(providerForm);
    setShowProviderForm(false);
    setProviderForm({ name: '', provider_type: 'anthropic', api_key: '', base_url: '' });
    api.getProviders().then(setProviders);
  };

  const startEditProvider = (p) => {
    setEditingProvider(p.id);
    setEditProviderForm({ name: p.name, provider_type: p.provider_type, api_key: '', base_url: p.base_url || '' });
    setShowProviderForm(false); // close add form if open
  };

  const cancelEditProvider = () => {
    setEditingProvider(null);
    setEditProviderForm({ name: '', provider_type: 'anthropic', api_key: '', base_url: '' });
  };

  const saveEditProvider = async (e) => {
    e.preventDefault();
    const payload = { name: editProviderForm.name, provider_type: editProviderForm.provider_type, base_url: editProviderForm.base_url || null };
    if (editProviderForm.api_key.trim()) payload.api_key = editProviderForm.api_key.trim();
    await api.updateProvider(editingProvider, payload);
    setEditingProvider(null);
    api.getProviders().then(setProviders);
  };

  const saveModel = async (e) => {
    e.preventDefault();
    const payload = { ...modelForm };
    payload.requests_per_minute = modelForm.requests_per_minute ? Number(modelForm.requests_per_minute) : null;
    await api.createModel(payload);
    setShowModelForm(false);
    api.getModels().then(setModels);
  };

  const startEditModel = (m) => {
    setEditingModel(m.id);
    setEditModelForm({
      provider_id: m.provider_id,
      name: m.name,
      model_id: m.model_id,
      context_window: m.context_window || 200000,
      max_tokens_per_run: m.max_tokens_per_run || 1000000,
      max_budget_usd: m.max_budget_usd || 50,
      input_price_per_mtok: m.input_price_per_mtok || 15,
      output_price_per_mtok: m.output_price_per_mtok || 75,
      requests_per_minute: m.requests_per_minute || '',
    });
    setShowModelForm(false); // close add form if open
  };

  const cancelEditModel = () => {
    setEditingModel(null);
  };

  const saveEditModel = async (e) => {
    e.preventDefault();
    await api.updateModel(editingModel, {
      provider_id: Number(editModelForm.provider_id),
      name: editModelForm.name,
      model_id: editModelForm.model_id,
      context_window: Number(editModelForm.context_window),
      max_tokens_per_run: Number(editModelForm.max_tokens_per_run),
      max_budget_usd: Number(editModelForm.max_budget_usd),
      input_price_per_mtok: Number(editModelForm.input_price_per_mtok),
      output_price_per_mtok: Number(editModelForm.output_price_per_mtok),
      requests_per_minute: editModelForm.requests_per_minute ? Number(editModelForm.requests_per_minute) : null,
    });
    setEditingModel(null);
    api.getModels().then(setModels);
  };

  const toggleTool = async (tool) => {
    await api.updateTool(tool.id, { is_enabled: !tool.is_enabled });
    api.getTools().then(setTools);
  };

  const saveJira = async (e) => {
    e.preventDefault();
    if (jiraConfig?.id) await api.updateJiraConfig(jiraConfig.id, jiraForm);
    else await api.saveJiraConfig(jiraForm);
    api.getJiraConfig().then(setJiraConfig);
  };

  const testJira = async () => {
    try {
      await api.testJiraConnection();
      setJiraTestResult({ ok: true, msg: 'Connected!' });
    } catch (e) {
      setJiraTestResult({ ok: false, msg: e.message });
    }
  };

  const tabs = [
    { id: 'providers', label: 'AI Providers' },
    { id: 'models', label: 'AI Models' },
    { id: 'tools', label: 'Security Tools' },
    { id: 'jira', label: 'Jira' },
  ];

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Settings</h1>
      <div className="flex gap-2 mb-6">
        {tabs.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-4 py-2 rounded text-sm ${tab === t.id ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'providers' && (
        <Section title="AI Providers">
          <div className="space-y-2 mb-4">
            {providers.map((p) => (
              <div key={p.id} className="border rounded overflow-hidden">
                {/* Provider row */}
                <div className="flex items-center justify-between p-3">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium">{p.name}</span>
                    <span className="text-sm text-gray-500 bg-gray-100 px-2 py-0.5 rounded">{p.provider_type}</span>
                    {p.api_key_masked && (
                      <span className="text-xs text-green-700 bg-green-50 border border-green-200 px-2 py-0.5 rounded font-mono">
                        {p.api_key_masked}
                      </span>
                    )}
                    {p.base_url && (
                      <span className="text-xs text-blue-600 font-mono truncate max-w-xs">{p.base_url}</span>
                    )}
                  </div>
                  <div className="flex gap-2 ml-2 shrink-0">
                    <button
                      onClick={() => editingProvider === p.id ? cancelEditProvider() : startEditProvider(p)}
                      className={`text-sm px-3 py-1 rounded border transition-colors ${
                        editingProvider === p.id
                          ? 'bg-gray-100 border-gray-300 text-gray-600 hover:bg-gray-200'
                          : 'bg-blue-50 border-blue-200 text-blue-600 hover:bg-blue-100'
                      }`}>
                      {editingProvider === p.id ? 'Cancel' : 'Edit'}
                    </button>
                    <button
                      onClick={() => { if (window.confirm(`Delete provider "${p.name}"? All linked models will also be deleted.`)) api.deleteProvider(p.id).then(() => api.getProviders().then(setProviders)); }}
                      className="text-sm px-3 py-1 rounded border border-red-200 bg-red-50 text-red-600 hover:bg-red-100 transition-colors">
                      Delete
                    </button>
                  </div>
                </div>

                {/* Inline edit form */}
                {editingProvider === p.id && (
                  <form onSubmit={saveEditProvider} className="border-t bg-gray-50 p-4 space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Name <span className="text-red-500">*</span></label>
                        <input
                          value={editProviderForm.name}
                          onChange={(e) => setEditProviderForm({ ...editProviderForm, name: e.target.value })}
                          className="border rounded px-3 py-2 w-full text-sm bg-white"
                          required />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Provider Type <span className="text-red-500">*</span></label>
                        <select
                          value={editProviderForm.provider_type}
                          onChange={(e) => setEditProviderForm({ ...editProviderForm, provider_type: e.target.value })}
                          className="border rounded px-3 py-2 w-full text-sm bg-white">
                          <option value="anthropic">Anthropic</option>
                          <option value="openai">OpenAI</option>
                          <option value="google">Google</option>
                          <option value="ollama">Ollama (Local)</option>
                        </select>
                      </div>
                    </div>
                    <div className="bg-blue-50 border border-blue-200 rounded p-3">
                      <label className="block text-xs font-semibold text-blue-800 mb-1">
                        🔑 Новый API Key
                        <span className="ml-1 font-normal text-blue-600">— текущий: {p.api_key_masked || 'не задан'}. Оставьте пустым чтобы не менять.</span>
                      </label>
                      <input
                        type="text"
                        placeholder="Вставьте сюда API ключ (sk-ant-...)"
                        value={editProviderForm.api_key}
                        onChange={(e) => setEditProviderForm({ ...editProviderForm, api_key: e.target.value.trim() })}
                        className="border border-blue-300 rounded px-3 py-2 w-full text-sm bg-white font-mono focus:ring-2 focus:ring-blue-400" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">Base URL <span className="text-gray-400 font-normal">(только для Ollama / Azure / self-hosted — оставьте пустым для Anthropic/OpenAI/Google)</span></label>
                      <input
                        placeholder="http://localhost:11434  (оставьте пустым для облачных провайдеров)"
                        value={editProviderForm.base_url}
                        onChange={(e) => setEditProviderForm({ ...editProviderForm, base_url: e.target.value })}
                        className="border rounded px-3 py-2 w-full text-sm bg-white text-gray-600" />
                    </div>
                    <div className="flex gap-2">
                      <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700 transition-colors">
                        Save Changes
                      </button>
                      <button type="button" onClick={cancelEditProvider} className="bg-gray-200 text-gray-700 px-4 py-2 rounded text-sm hover:bg-gray-300 transition-colors">
                        Cancel
                      </button>
                    </div>
                  </form>
                )}
              </div>
            ))}
          </div>
          <button onClick={() => setShowProviderForm(!showProviderForm)} className="text-blue-600 text-sm hover:underline">+ Add Provider</button>
          {showProviderForm && (
            <form onSubmit={saveProvider} className="mt-3 space-y-2 border-t pt-3">
              <input placeholder="Name (e.g. Anthropic)" value={providerForm.name} onChange={(e) => setProviderForm({ ...providerForm, name: e.target.value })} className="border rounded px-3 py-2 w-full text-sm" required />
              <select value={providerForm.provider_type} onChange={(e) => setProviderForm({ ...providerForm, provider_type: e.target.value })} className="border rounded px-3 py-2 w-full text-sm">
                <option value="anthropic">Anthropic</option>
                <option value="openai">OpenAI</option>
                <option value="google">Google</option>
                <option value="ollama">Ollama (Local)</option>
              </select>
              <input type="password" placeholder="API Key" value={providerForm.api_key} onChange={(e) => setProviderForm({ ...providerForm, api_key: e.target.value })} className="border rounded px-3 py-2 w-full text-sm" />
              <input placeholder="Base URL (optional)" value={providerForm.base_url} onChange={(e) => setProviderForm({ ...providerForm, base_url: e.target.value })} className="border rounded px-3 py-2 w-full text-sm" />
              <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded text-sm">Save Provider</button>
            </form>
          )}
        </Section>
      )}

      {tab === 'models' && (
        <Section title="AI Models">
          <div className="space-y-2 mb-4">
            {models.map((m) => {
              const providerName = providers.find((p) => p.id === m.provider_id)?.name || `Provider #${m.provider_id}`;
              return (
                <div key={m.id} className="border rounded overflow-hidden">
                  {/* Model row */}
                  <div className="flex items-center justify-between p-3">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium">{m.name}</span>
                      <span className="text-xs font-mono text-blue-700 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded">{m.model_id}</span>
                      <span className="text-xs text-gray-500 bg-gray-100 px-2 py-0.5 rounded">{providerName}</span>
                      <span className="text-xs text-gray-400">ctx: {((m.context_window || 0) / 1000).toFixed(0)}K</span>
                      <span className="text-xs text-gray-400">budget: ${m.max_budget_usd}</span>
                      {m.input_price_per_mtok != null && (
                        <span className="text-xs text-gray-400">in: ${m.input_price_per_mtok}/MTok</span>
                      )}
                    </div>
                    <div className="flex gap-2 ml-2 shrink-0">
                      <button
                        onClick={() => editingModel === m.id ? cancelEditModel() : startEditModel(m)}
                        className={`text-sm px-3 py-1 rounded border transition-colors ${
                          editingModel === m.id
                            ? 'bg-gray-100 border-gray-300 text-gray-600 hover:bg-gray-200'
                            : 'bg-blue-50 border-blue-200 text-blue-600 hover:bg-blue-100'
                        }`}>
                        {editingModel === m.id ? 'Cancel' : 'Edit'}
                      </button>
                      <button
                        onClick={() => { if (window.confirm(`Delete model "${m.name}"?`)) api.deleteModel(m.id).then(() => api.getModels().then(setModels)); }}
                        className="text-sm px-3 py-1 rounded border border-red-200 bg-red-50 text-red-600 hover:bg-red-100 transition-colors">
                        Delete
                      </button>
                    </div>
                  </div>

                  {/* Inline edit form */}
                  {editingModel === m.id && (
                    <form onSubmit={saveEditModel} className="border-t bg-gray-50 p-4 space-y-3">
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-medium text-gray-600 mb-1">AI Provider <span className="text-red-500">*</span></label>
                          <select value={editModelForm.provider_id} onChange={(e) => setEditModelForm({ ...editModelForm, provider_id: e.target.value })} className="border rounded px-3 py-2 w-full text-sm bg-white" required>
                            <option value="">Select Provider...</option>
                            {providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                          </select>
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-gray-600 mb-1">Display Name <span className="text-red-500">*</span></label>
                          <input value={editModelForm.name} onChange={(e) => setEditModelForm({ ...editModelForm, name: e.target.value })} className="border rounded px-3 py-2 w-full text-sm bg-white" required />
                        </div>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Model ID <span className="text-red-500">*</span> <span className="text-gray-400 font-normal">— идентификатор из API</span></label>
                        <input value={editModelForm.model_id} onChange={(e) => setEditModelForm({ ...editModelForm, model_id: e.target.value })} className="border rounded px-3 py-2 w-full text-sm bg-white font-mono" required />
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-medium text-gray-600 mb-1">Context Window <span className="text-gray-400 font-normal">(токены)</span></label>
                          <input type="number" value={editModelForm.context_window} onChange={(e) => setEditModelForm({ ...editModelForm, context_window: e.target.value })} className="border rounded px-3 py-2 w-full text-sm bg-white" />
                          <p className="text-xs text-gray-400 mt-0.5">Claude: 200000, GPT-4o: 128000</p>
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-gray-600 mb-1">Max Tokens/Run <span className="text-gray-400 font-normal">(лимит за скан)</span></label>
                          <input type="number" value={editModelForm.max_tokens_per_run} onChange={(e) => setEditModelForm({ ...editModelForm, max_tokens_per_run: e.target.value })} className="border rounded px-3 py-2 w-full text-sm bg-white" />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-gray-600 mb-1">Max Budget ($) <span className="text-gray-400 font-normal">(стоп при достижении)</span></label>
                          <input type="number" step="0.01" value={editModelForm.max_budget_usd} onChange={(e) => setEditModelForm({ ...editModelForm, max_budget_usd: e.target.value })} className="border rounded px-3 py-2 w-full text-sm bg-white" />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-gray-600 mb-1">Input $/MTok</label>
                          <input type="number" step="0.01" value={editModelForm.input_price_per_mtok} onChange={(e) => setEditModelForm({ ...editModelForm, input_price_per_mtok: e.target.value })} className="border rounded px-3 py-2 w-full text-sm bg-white" />
                          <p className="text-xs text-gray-400 mt-0.5">Sonnet: $3, Opus: $15, Haiku: $0.8</p>
                        </div>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Output $/MTok</label>
                        <input type="number" step="0.01" value={editModelForm.output_price_per_mtok} onChange={(e) => setEditModelForm({ ...editModelForm, output_price_per_mtok: e.target.value })} className="border rounded px-3 py-2 w-full text-sm bg-white" />
                        <p className="text-xs text-gray-400 mt-0.5">Sonnet: $15, Opus: $75, Haiku: $4</p>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">
                          Rate Limit (RPM) <span className="text-gray-400 font-normal">— запросов в минуту, 0 = без ограничений</span>
                        </label>
                        <input type="number" min="0" placeholder="Оставьте пустым — без лимита" value={editModelForm.requests_per_minute} onChange={(e) => setEditModelForm({ ...editModelForm, requests_per_minute: e.target.value })} className="border rounded px-3 py-2 w-full text-sm bg-white" />
                        <p className="text-xs text-gray-400 mt-0.5">
                          Tier 1 Anthropic: Sonnet = 5 RPM, Haiku = 50 RPM. Установите лимит чтобы система автоматически соблюдала паузы между запросами.
                        </p>
                      </div>
                      <div className="flex gap-2">
                        <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700 transition-colors">Save Changes</button>
                        <button type="button" onClick={cancelEditModel} className="bg-gray-200 text-gray-700 px-4 py-2 rounded text-sm hover:bg-gray-300 transition-colors">Cancel</button>
                      </div>
                    </form>
                  )}
                </div>
              );
            })}
          </div>
          <button onClick={() => { setShowModelForm(!showModelForm); setEditingModel(null); }} className="text-blue-600 text-sm hover:underline">+ Add Model</button>
          {showModelForm && (
            <form onSubmit={saveModel} className="mt-3 space-y-3 border-t pt-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">AI Provider <span className="text-red-500">*</span></label>
                <select value={modelForm.provider_id} onChange={(e) => setModelForm({ ...modelForm, provider_id: Number(e.target.value) })} className="border rounded px-3 py-2 w-full text-sm" required>
                  <option value="">Select Provider...</option>
                  {providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Display Name <span className="text-red-500">*</span> <span className="text-gray-400 font-normal">— произвольное название (напр. "Claude Sonnet 4")</span></label>
                <input placeholder="Claude Sonnet 4" value={modelForm.name} onChange={(e) => setModelForm({ ...modelForm, name: e.target.value })} className="border rounded px-3 py-2 w-full text-sm" required />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Model ID <span className="text-red-500">*</span> <span className="text-gray-400 font-normal">— идентификатор из API (напр. claude-sonnet-4-20250514)</span></label>
                <input placeholder="claude-sonnet-4-20250514" value={modelForm.model_id} onChange={(e) => setModelForm({ ...modelForm, model_id: e.target.value })} className="border rounded px-3 py-2 w-full text-sm font-mono" required />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Context Window <span className="text-gray-400 font-normal">(токены)</span></label>
                  <input type="number" placeholder="200000" value={modelForm.context_window} onChange={(e) => setModelForm({ ...modelForm, context_window: Number(e.target.value) })} className="border rounded px-3 py-2 w-full text-sm" />
                  <p className="text-xs text-gray-400 mt-0.5">Claude: 200000, GPT-4o: 128000</p>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Max Tokens/Run <span className="text-gray-400 font-normal">(лимит за весь скан)</span></label>
                  <input type="number" placeholder="1000000" value={modelForm.max_tokens_per_run} onChange={(e) => setModelForm({ ...modelForm, max_tokens_per_run: Number(e.target.value) })} className="border rounded px-3 py-2 w-full text-sm" />
                  <p className="text-xs text-gray-400 mt-0.5">Рекомендуется: 1000000</p>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Max Budget ($) <span className="text-gray-400 font-normal">(стоп при достижении)</span></label>
                  <input type="number" step="0.01" placeholder="10" value={modelForm.max_budget_usd} onChange={(e) => setModelForm({ ...modelForm, max_budget_usd: Number(e.target.value) })} className="border rounded px-3 py-2 w-full text-sm" />
                  <p className="text-xs text-gray-400 mt-0.5">Скан остановится автоматически</p>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Input $/MTok <span className="text-gray-400 font-normal">(цена входящих токенов)</span></label>
                  <input type="number" step="0.01" placeholder="3" value={modelForm.input_price_per_mtok} onChange={(e) => setModelForm({ ...modelForm, input_price_per_mtok: Number(e.target.value) })} className="border rounded px-3 py-2 w-full text-sm" />
                  <p className="text-xs text-gray-400 mt-0.5">Sonnet: $3, Opus: $15, Haiku: $0.8</p>
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Output $/MTok <span className="text-gray-400 font-normal">(цена исходящих токенов)</span></label>
                <input type="number" step="0.01" placeholder="15" value={modelForm.output_price_per_mtok} onChange={(e) => setModelForm({ ...modelForm, output_price_per_mtok: Number(e.target.value) })} className="border rounded px-3 py-2 w-full text-sm" />
                <p className="text-xs text-gray-400 mt-0.5">Sonnet: $15, Opus: $75, Haiku: $4 — см. console.anthropic.com/settings/pricing</p>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Rate Limit (RPM) <span className="text-gray-400 font-normal">— запросов в минуту, оставьте пустым если нет ограничений</span></label>
                <input type="number" min="0" placeholder="Напр: 5 для Sonnet Tier1, 50 для Haiku Tier1" value={modelForm.requests_per_minute} onChange={(e) => setModelForm({ ...modelForm, requests_per_minute: e.target.value })} className="border rounded px-3 py-2 w-full text-sm" />
                <p className="text-xs text-gray-400 mt-0.5">Система будет делать паузы между chunk'ами чтобы не превышать лимит</p>
              </div>
              <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded text-sm">Save Model</button>
            </form>
          )}
        </Section>
      )}

      {tab === 'tools' && (
        <Section title="Security Tools">
          <div className="space-y-2">
            {tools.map((t) => (
              <div key={t.id} className="flex items-center justify-between p-3 border rounded">
                <div className="flex items-center">
                  <span className="font-medium">{t.tool_name}</span>
                  <ToolInfoPopover toolName={t.tool_name} />
                  {t.install_command && <span className="ml-2 text-xs text-gray-400 font-mono">{t.install_command}</span>}
                </div>
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={t.is_enabled} onChange={() => toggleTool(t)} className="rounded" />
                  <span className="text-sm">{t.is_enabled ? 'Enabled' : 'Disabled'}</span>
                </label>
              </div>
            ))}
          </div>
        </Section>
      )}

      {tab === 'jira' && (
        <Section title="Jira Integration">
          <form onSubmit={saveJira} className="space-y-3">
            <input placeholder="Jira Base URL (e.g. https://company.atlassian.net)" value={jiraForm.base_url||''} onChange={(e) => setJiraForm({ ...jiraForm, base_url: e.target.value })} className="border rounded px-3 py-2 w-full text-sm" required />
            <input placeholder="User Email" value={jiraForm.user_email||''} onChange={(e) => setJiraForm({ ...jiraForm, user_email: e.target.value })} className="border rounded px-3 py-2 w-full text-sm" />
            <input type="password" placeholder="API Token" value={jiraForm.api_token||''} onChange={(e) => setJiraForm({ ...jiraForm, api_token: e.target.value })} className="border rounded px-3 py-2 w-full text-sm" />
            <input placeholder="Project Key (e.g. SEC)" value={jiraForm.project_key||''} onChange={(e) => setJiraForm({ ...jiraForm, project_key: e.target.value })} className="border rounded px-3 py-2 w-full text-sm" required />
            <div className="flex gap-2">
              <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded text-sm">Save</button>
              <button type="button" onClick={testJira} className="bg-gray-200 px-4 py-2 rounded text-sm">Test Connection</button>
            </div>
            {jiraTestResult && (
              <p className={`text-sm ${jiraTestResult.ok ? 'text-green-600' : 'text-red-600'}`}>{jiraTestResult.msg}</p>
            )}
          </form>
        </Section>
      )}
    </div>
  );
}
