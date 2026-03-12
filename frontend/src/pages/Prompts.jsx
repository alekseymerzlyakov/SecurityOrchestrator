import { useState, useEffect } from 'react';
import { api } from '../api/client';

// Categories that map to real use-cases in the engine
const CATEGORIES = [
  { id: 'ai_only', label: 'AI Only', color: 'bg-purple-100 text-purple-700', desc: 'Полный аудит без SAST — AI сканирует весь репозиторий самостоятельно' },
  { id: 'hybrid', label: 'Hybrid', color: 'bg-green-100 text-green-700', desc: 'Углублённый анализ — AI верифицирует находки SAST и ищет цепочки уязвимостей' },
  { id: 'general', label: 'General', color: 'bg-gray-100 text-gray-700', desc: 'Универсальный промпт — подходит для любого режима' },
];

const CATEGORY_MAP = Object.fromEntries(CATEGORIES.map((c) => [c.id, c]));

// Detect built-in system prompts by name prefix
const isBuiltIn = (name) =>
  name.startsWith('AI-Only:') || name.startsWith('Hybrid:') || name.startsWith('Report:');

export default function Prompts() {
  const [prompts, setPrompts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [categoryFilter, setCategoryFilter] = useState('');
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ name: '', category: 'general', content: '' });
  const [showForm, setShowForm] = useState(false);

  const loadPrompts = () => {
    api.getPrompts(categoryFilter || undefined)
      .then((data) => setPrompts(Array.isArray(data) ? data : []))
      .catch(() => setPrompts([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadPrompts(); }, [categoryFilter]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      if (editing) {
        await api.updatePrompt(editing.id, form);
      } else {
        await api.createPrompt(form);
      }
      resetForm();
      loadPrompts();
    } catch (err) { alert(err.message); }
  };

  const resetForm = () => {
    setForm({ name: '', category: 'general', content: '' });
    setEditing(null);
    setShowForm(false);
  };

  const startEdit = (prompt) => {
    setEditing(prompt);
    setForm({ name: prompt.name, category: prompt.category || 'general', content: prompt.content });
    setShowForm(true);
  };

  const handleDelete = async (id) => {
    if (!confirm('Delete this prompt?')) return;
    await api.deletePrompt(id);
    loadPrompts();
  };

  const setDefault = async (id) => {
    await api.setDefaultPrompt(id);
    loadPrompts();
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-2">
        <h1 className="text-2xl font-bold">Prompts</h1>
        <button onClick={() => { resetForm(); setShowForm(!showForm); }}
          className="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 text-sm">
          {showForm ? 'Cancel' : '+ Create Prompt'}
        </button>
      </div>
      <p className="text-sm text-gray-500 mb-4">
        Промпты автоматически выбираются по режиму скана. В PipelineBuilder можно выбрать промпт вручную — он переопределит автоматический.
      </p>

      {/* Category filter */}
      <div className="flex gap-2 mb-5 flex-wrap">
        <button onClick={() => setCategoryFilter('')}
          className={`px-3 py-1 rounded text-sm font-medium ${!categoryFilter ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}>
          Все
        </button>
        {CATEGORIES.map((cat) => (
          <button key={cat.id} onClick={() => setCategoryFilter(cat.id)}
            className={`px-3 py-1 rounded text-sm font-medium ${categoryFilter === cat.id ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}>
            {cat.label}
          </button>
        ))}
      </div>

      {/* Mode info cards */}
      {!categoryFilter && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-6">
          {CATEGORIES.filter(c => c.id !== 'general').map((cat) => (
            <div key={cat.id} className="bg-white rounded-lg border border-gray-200 p-3 flex gap-3 items-start">
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium shrink-0 mt-0.5 ${cat.color}`}>{cat.label}</span>
              <p className="text-xs text-gray-600">{cat.desc}</p>
            </div>
          ))}
        </div>
      )}

      {/* Create/Edit Form */}
      {showForm && (
        <form onSubmit={handleSubmit} className="bg-white rounded-lg shadow p-5 mb-6 space-y-4 border border-blue-100">
          <h2 className="font-semibold text-gray-800">{editing ? 'Редактировать промпт' : 'Создать промпт'}</h2>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Название <span className="text-red-500">*</span>
              </label>
              <input
                placeholder="Hybrid: Мой кастомный промпт"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="border rounded px-3 py-2 text-sm w-full"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Категория / Режим <span className="text-red-500">*</span>
              </label>
              <select
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
                className="border rounded px-3 py-2 text-sm w-full"
              >
                {CATEGORIES.map((c) => (
                  <option key={c.id} value={c.id}>{c.label} — {c.desc.split('—')[0].trim()}</option>
                ))}
              </select>
              <p className="text-xs text-gray-400 mt-1">
                {CATEGORY_MAP[form.category]?.desc}
              </p>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Содержимое промпта <span className="text-red-500">*</span>
              <span className="text-gray-400 font-normal ml-2">— системный промпт для AI, описывает задачу анализа и формат JSON ответа</span>
            </label>
            <textarea
              value={form.content}
              onChange={(e) => setForm({ ...form, content: e.target.value })}
              className="border rounded px-3 py-2 w-full text-sm font-mono"
              style={{ minHeight: '420px' }}
              placeholder="You are a security auditor..."
              required
            />
          </div>

          <div className="flex gap-2">
            <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700">
              {editing ? 'Сохранить изменения' : 'Создать промпт'}
            </button>
            <button type="button" onClick={resetForm} className="bg-gray-100 text-gray-700 px-4 py-2 rounded text-sm hover:bg-gray-200">
              Отмена
            </button>
          </div>
        </form>
      )}

      {/* Prompt list */}
      {loading ? (
        <p className="text-gray-400 text-sm">Загрузка...</p>
      ) : prompts.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <p className="text-sm">Нет промптов. Они создаются автоматически при первом запуске backend.</p>
          <p className="text-xs mt-1">Перезапустите backend если промпты не появились.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {prompts.map((p) => {
            const catInfo = CATEGORY_MAP[p.category] || CATEGORY_MAP['general'];
            const builtIn = isBuiltIn(p.name);
            return (
              <div key={p.id} className="bg-white rounded-lg shadow p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <h3 className="font-medium text-gray-900 text-sm">{p.name}</h3>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${catInfo.color}`}>
                        {catInfo.label}
                      </span>
                      {builtIn && (
                        <span className="text-xs bg-yellow-50 text-yellow-700 border border-yellow-200 px-2 py-0.5 rounded-full">
                          Built-in
                        </span>
                      )}
                      {p.is_default && (
                        <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
                          Default
                        </span>
                      )}
                      <span className="text-xs text-gray-400">v{p.version}</span>
                    </div>
                    {catInfo && (
                      <p className="text-xs text-gray-500 mb-2">{catInfo.desc}</p>
                    )}
                  </div>
                  <div className="flex gap-3 shrink-0 text-xs">
                    {!p.is_default && (
                      <button onClick={() => setDefault(p.id)} className="text-green-600 hover:underline">
                        Set Default
                      </button>
                    )}
                    <button onClick={() => startEdit(p)} className="text-blue-600 hover:underline">Edit</button>
                    {!builtIn && (
                      <button onClick={() => handleDelete(p.id)} className="text-red-600 hover:underline">Delete</button>
                    )}
                  </div>
                </div>
                <pre className="text-xs text-gray-500 max-h-20 overflow-auto bg-gray-50 p-2 rounded font-mono leading-relaxed">
                  {p.content.substring(0, 400)}{p.content.length > 400 ? '...' : ''}
                </pre>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
