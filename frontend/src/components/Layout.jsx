import { useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import { useScanStore } from '../store/scanStore';
import { wsClient } from '../api/websocket';
import {
  ShieldCheckIcon,
  HomeIcon,
  FolderIcon,
  PlayIcon,
  EyeIcon,
  ExclamationTriangleIcon,
  DocumentTextIcon,
  ChatBubbleLeftRightIcon,
  CogIcon,
} from '@heroicons/react/24/outline';

const navItems = [
  { to: '/', icon: HomeIcon, label: 'Dashboard' },
  { to: '/projects', icon: FolderIcon, label: 'Projects' },
  { to: '/pipeline', icon: PlayIcon, label: 'Scan Pipeline' },
  { to: '/monitor', icon: EyeIcon, label: 'Live Monitor' },
  { to: '/findings', icon: ExclamationTriangleIcon, label: 'Findings' },
  { to: '/reports', icon: DocumentTextIcon, label: 'Reports' },
  { to: '/prompts', icon: ChatBubbleLeftRightIcon, label: 'Prompts' },
  { to: '/settings', icon: CogIcon, label: 'Settings' },
];

export default function Layout({ children }) {
  const { isConnected, setConnected, updateProgress, addFinding, scanComplete, initSteps, completeStep, updateStepStatus } =
    useScanStore();

  useEffect(() => {
    wsClient.connect();
    const unsubs = [
      wsClient.on('connected', setConnected),

      // Initialize step list when scan starts — backend sends step names
      wsClient.on('scan_started', (data) => {
        if (Array.isArray(data.step_names)) {
          initSteps(data.step_names);
        }
      }),

      // Progress update — also updates step statuses inside the store
      wsClient.on('scan_progress', updateProgress),

      // Step completed — update findings count for that step
      wsClient.on('step_complete', (data) => {
        completeStep(data.step_name, data.findings_count, data.status, data.error);
      }),

      // Intermediate status message from a running tool (e.g. yarn audit progress)
      wsClient.on('step_status', (data) => {
        updateStepStatus(data.step_name, data.message, data.interim_count);
      }),

      wsClient.on('new_finding', addFinding),
      wsClient.on('scan_complete', scanComplete),
    ];
    return () => {
      unsubs.forEach((fn) => fn());
      wsClient.disconnect();
    };
  }, []);

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="w-64 bg-gray-900 text-white flex flex-col">
        <div className="p-4 flex items-center gap-2 border-b border-gray-700">
          <ShieldCheckIcon className="h-8 w-8 text-green-400" />
          <div>
            <h1 className="text-lg font-bold">AISO</h1>
            <p className="text-xs text-gray-400">Security Orchestrator</p>
          </div>
        </div>

        <nav className="flex-1 py-4">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                  isActive
                    ? 'bg-gray-800 text-white border-r-2 border-green-400'
                    : 'text-gray-300 hover:bg-gray-800 hover:text-white'
                }`
              }
            >
              <Icon className="h-5 w-5" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-gray-700">
          <div className="flex items-center gap-2 text-xs">
            <span
              className={`h-2 w-2 rounded-full ${isConnected ? 'bg-green-400' : 'bg-red-400'}`}
            />
            <span className="text-gray-400">
              {isConnected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="p-6">{children}</div>
      </main>
    </div>
  );
}
