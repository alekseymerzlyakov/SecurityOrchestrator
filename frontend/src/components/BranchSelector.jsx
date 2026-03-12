import { useState, useEffect } from 'react';
import { api } from '../api/client';

/**
 * BranchSelector — multi-select branch picker.
 *
 * Props:
 *   projectId  — project ID to load branches for
 *   value      — array of selected branch names, e.g. ["develop", "main"]
 *   onChange   — called with new array of selected names
 *   single     — if true, behaves as single-select (radio-style), value is a string
 */
export default function BranchSelector({ projectId, value, onChange, single = false }) {
  const [branches, setBranches] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!projectId) {
      setBranches([]);
      return;
    }
    setLoading(true);
    api
      .getBranches(projectId)
      .then((data) => {
        // API returns { branches: [...], current: "..." }
        const list = Array.isArray(data) ? data : (data?.branches ?? []);
        // Normalize: if items are strings, convert to { name, is_current } objects
        const normalized = list.map((b) =>
          typeof b === 'string'
            ? { name: b, is_current: b === data?.current }
            : b
        );
        setBranches(normalized);
      })
      .catch(() => setBranches([]))
      .finally(() => setLoading(false));
  }, [projectId]);

  if (loading) return <span className="text-sm text-gray-400">Loading branches...</span>;
  if (!projectId) return <span className="text-sm text-gray-400">Select a project first</span>;
  if (branches.length === 0) return <span className="text-sm text-gray-400">No branches found</span>;

  // ── Single-select mode (dropdown) ──────────────────────────────────────────
  if (single) {
    return (
      <select
        className="border rounded px-3 py-2 text-sm w-full"
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">Select branch...</option>
        {branches.map((b) => (
          <option key={b.name} value={b.name}>
            {b.name} {b.is_current ? '(current)' : ''}
          </option>
        ))}
      </select>
    );
  }

  // ── Multi-select mode (checkbox list) ──────────────────────────────────────
  const selected = Array.isArray(value) ? value : (value ? [value] : []);

  const toggle = (name) => {
    if (selected.includes(name)) {
      onChange(selected.filter((n) => n !== name));
    } else {
      onChange([...selected, name]);
    }
  };

  const selectAll = () => onChange(branches.map((b) => b.name));
  const clearAll  = () => onChange([]);

  return (
    <div>
      {/* Quick actions */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-gray-500">
          {selected.length === 0
            ? 'Нет выбранных веток'
            : `Выбрано: ${selected.length} из ${branches.length}`}
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={selectAll}
            className="text-xs text-blue-600 hover:underline"
          >
            Все
          </button>
          {selected.length > 0 && (
            <button
              type="button"
              onClick={clearAll}
              className="text-xs text-gray-400 hover:underline"
            >
              Сбросить
            </button>
          )}
        </div>
      </div>

      {/* Branch list — scrollable if many branches */}
      <div className="border rounded-lg divide-y divide-gray-100 max-h-52 overflow-y-auto">
        {branches.map((b) => {
          const checked = selected.includes(b.name);
          return (
            <label
              key={b.name}
              className={`flex items-center gap-2.5 px-3 py-2 cursor-pointer hover:bg-gray-50 transition-colors ${
                checked ? 'bg-blue-50' : ''
              }`}
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={() => toggle(b.name)}
                className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              <span className={`text-sm ${checked ? 'font-medium text-blue-700' : 'text-gray-700'}`}>
                {b.name}
              </span>
              {b.is_current && (
                <span className="ml-auto text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded-full">
                  current
                </span>
              )}
            </label>
          );
        })}
      </div>

      {selected.length > 1 && (
        <p className="text-xs text-gray-400 mt-1.5">
          Будет запущено {selected.length} отдельных скана — по одному на каждую ветку
        </p>
      )}
    </div>
  );
}
