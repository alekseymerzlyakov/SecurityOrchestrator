import SeverityBadge from './SeverityBadge';
import { STATUS_COLORS } from '../utils/formatters';

export default function FindingCard({ finding, onClick, onCreateJira }) {
  return (
    <div
      className="bg-white rounded-lg shadow p-4 hover:shadow-md transition-shadow cursor-pointer border-l-4"
      style={{
        borderLeftColor:
          finding.severity === 'critical'
            ? '#dc2626'
            : finding.severity === 'high'
              ? '#f97316'
              : finding.severity === 'medium'
                ? '#eab308'
                : '#60a5fa',
      }}
      onClick={() => onClick?.(finding)}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <SeverityBadge severity={finding.severity} />
            <span className={`px-2 py-0.5 rounded text-xs ${STATUS_COLORS[finding.status]}`}>
              {finding.status}
            </span>
            {finding.tool_name && (
              <span className="text-xs text-gray-400">{finding.tool_name}</span>
            )}
          </div>
          <h4 className="font-medium text-gray-900">{finding.title}</h4>
          {finding.file_path && (
            <p className="text-sm text-gray-500 mt-1 font-mono">
              {finding.file_path}
              {finding.line_start ? `:${finding.line_start}` : ''}
            </p>
          )}
          {finding.cwe_id && (
            <span className="text-xs text-gray-400">{finding.cwe_id}</span>
          )}
        </div>
        {onCreateJira && !finding.jira_ticket_id && (
          <button
            className="text-xs bg-blue-50 text-blue-600 px-2 py-1 rounded hover:bg-blue-100"
            onClick={(e) => {
              e.stopPropagation();
              onCreateJira(finding.id);
            }}
          >
            Jira
          </button>
        )}
      </div>
    </div>
  );
}
