import {
  CheckCircleIcon,
  XCircleIcon,
  ArrowPathIcon,
  ClockIcon,
} from '@heroicons/react/24/solid';
import ToolInfoPopover from './ToolInfoPopover';

const STATUS_ICON = {
  pending: ClockIcon,
  running: ArrowPathIcon,
  completed: CheckCircleIcon,
  failed: XCircleIcon,
  skipped: XCircleIcon,
};

const STATUS_COLOR = {
  pending: 'text-gray-400',
  running: 'text-blue-500 animate-spin',
  completed: 'text-green-500',
  failed: 'text-red-500',
  skipped: 'text-gray-300',
};

export default function PipelineStep({ step, onToggle, onRemove, draggable }) {
  const Icon = STATUS_ICON[step.status] || ClockIcon;
  const color = STATUS_COLOR[step.status] || 'text-gray-400';

  return (
    <div
      className={`flex items-center gap-3 p-3 bg-white rounded-lg shadow-sm border ${
        step.enabled === false ? 'opacity-50' : ''
      }`}
    >
      <Icon className={`h-5 w-5 ${color}`} />
      <div className="flex-1 flex items-center">
        <span className="font-medium text-sm">{step.tool_name}</span>
        <ToolInfoPopover toolName={step.tool_name} />
        {step.findings_count > 0 && (
          <span className="ml-2 text-xs text-red-500">{step.findings_count} findings</span>
        )}
      </div>
      {onToggle && (
        <label className="flex items-center">
          <input
            type="checkbox"
            checked={step.enabled !== false}
            onChange={() => onToggle(step.tool_name)}
            className="rounded"
          />
        </label>
      )}
      {onRemove && (
        <button
          className="text-gray-400 hover:text-red-500 text-sm"
          onClick={() => onRemove(step.tool_name)}
        >
          Remove
        </button>
      )}
    </div>
  );
}
