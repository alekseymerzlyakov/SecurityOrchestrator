import { SEVERITY_COLORS } from '../utils/formatters';

export default function SeverityBadge({ severity }) {
  const color = SEVERITY_COLORS[severity] || SEVERITY_COLORS.info;
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium uppercase ${color}`}>
      {severity}
    </span>
  );
}
