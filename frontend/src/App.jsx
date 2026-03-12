import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Projects from './pages/Projects';
import Settings from './pages/Settings';
import PipelineBuilder from './pages/PipelineBuilder';
import LiveMonitor from './pages/LiveMonitor';
import Findings from './pages/Findings';
import Reports from './pages/Reports';
import Prompts from './pages/Prompts';

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/projects" element={<Projects />} />
        <Route path="/pipeline" element={<PipelineBuilder />} />
        <Route path="/monitor" element={<LiveMonitor />} />
        <Route path="/findings" element={<Findings />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/prompts" element={<Prompts />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
