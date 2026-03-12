import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { formatDate } from '../utils/formatters';
import { FolderIcon, TrashIcon, ChevronDownIcon, ChevronUpIcon } from '@heroicons/react/24/outline';

export default function Projects() {
  const [projects, setProjects] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', repo_path: '', repo_url: '' });
  const [expanded, setExpanded] = useState(null);
  const [branches, setBranches] = useState([]);
  const [authors, setAuthors] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadProjects = () => {
    api.getProjects().then(setProjects).catch(() => setProjects([])).finally(() => setLoading(false));
  };

  useEffect(() => { loadProjects(); }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await api.createProject(form);
      setForm({ name: '', repo_path: '', repo_url: '' });
      setShowForm(false);
      loadProjects();
    } catch (err) {
      alert(err.message);
    }
  };

  const handleExpand = async (id) => {
    if (expanded === id) { setExpanded(null); return; }
    setExpanded(id);
    try {
      const [b, a] = await Promise.all([api.getBranches(id), api.getAuthors(id)]);
      setBranches(Array.isArray(b) ? b : []);
      setAuthors(Array.isArray(a) ? a : []);
    } catch { setBranches([]); setAuthors([]); }
  };

  const handleDelete = async (id) => {
    if (!confirm('Delete this project?')) return;
    await api.deleteProject(id);
    loadProjects();
  };

  if (loading) return <div className="text-gray-400">Loading...</div>;

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Projects</h1>
        <button onClick={() => setShowForm(!showForm)} className="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 text-sm">
          {showForm ? 'Cancel' : '+ Add Project'}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="bg-white rounded-lg shadow p-4 mb-6 space-y-3">
          <input placeholder="Project Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
            className="border rounded px-3 py-2 w-full text-sm" required />
          <input placeholder="Repository Path (e.g. /Users/.../repo)" value={form.repo_path}
            onChange={(e) => setForm({ ...form, repo_path: e.target.value })}
            className="border rounded px-3 py-2 w-full text-sm font-mono" required />
          <input placeholder="Repository URL (optional)" value={form.repo_url}
            onChange={(e) => setForm({ ...form, repo_url: e.target.value })}
            className="border rounded px-3 py-2 w-full text-sm" />
          <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded text-sm">Create Project</button>
        </form>
      )}

      <div className="space-y-3">
        {projects.map((p) => (
          <div key={p.id} className="bg-white rounded-lg shadow">
            <div className="p-4 flex items-center gap-3">
              <FolderIcon className="h-6 w-6 text-blue-500" />
              <div className="flex-1">
                <h3 className="font-medium">{p.name}</h3>
                <p className="text-sm text-gray-500 font-mono">{p.repo_path}</p>
                <p className="text-xs text-gray-400">{formatDate(p.created_at)}</p>
              </div>
              <button onClick={() => handleExpand(p.id)} className="text-gray-400 hover:text-blue-500">
                {expanded === p.id ? <ChevronUpIcon className="h-5 w-5" /> : <ChevronDownIcon className="h-5 w-5" />}
              </button>
              <button onClick={() => handleDelete(p.id)} className="text-gray-400 hover:text-red-500">
                <TrashIcon className="h-5 w-5" />
              </button>
            </div>

            {expanded === p.id && (
              <div className="border-t px-4 py-3 grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <h4 className="font-medium text-sm mb-2">Branches ({branches.length})</h4>
                  <div className="max-h-48 overflow-auto space-y-1">
                    {branches.map((b) => (
                      <div key={b.name} className="text-sm font-mono flex items-center gap-2">
                        {b.is_current && <span className="h-2 w-2 rounded-full bg-green-400" />}
                        {b.name}
                      </div>
                    ))}
                    {branches.length === 0 && <p className="text-gray-400 text-sm">No branches found</p>}
                  </div>
                </div>
                <div>
                  <h4 className="font-medium text-sm mb-2">Authors</h4>
                  <div className="max-h-48 overflow-auto space-y-1">
                    {authors.map((a, i) => (
                      <div key={i} className="text-sm flex justify-between">
                        <span>{a.name}</span>
                        <span className="text-gray-400">{a.commits} commits</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
        {projects.length === 0 && <p className="text-gray-400">No projects yet. Add one to get started.</p>}
      </div>
    </div>
  );
}
