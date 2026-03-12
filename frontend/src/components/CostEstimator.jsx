import { formatNumber, formatCost } from '../utils/formatters';

export default function CostEstimator({ estimate }) {
  if (!estimate) return null;

  return (
    <div className="bg-blue-50 rounded-lg p-4 border border-blue-200">
      <h3 className="text-sm font-medium text-blue-800 mb-2">Cost Estimate</h3>
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div className="text-gray-600">Total tokens:</div>
        <div className="font-mono">{formatNumber(estimate.total_tokens || 0)}</div>
        <div className="text-gray-600">Estimated chunks:</div>
        <div className="font-mono">{estimate.estimated_chunks || 0}</div>
        <div className="text-gray-600">Input cost:</div>
        <div className="font-mono">{formatCost(estimate.estimated_input_cost || 0)}</div>
        <div className="text-gray-600">Output cost:</div>
        <div className="font-mono">{formatCost(estimate.estimated_output_cost || 0)}</div>
        <div className="text-gray-600 font-medium">Total cost:</div>
        <div className="font-mono font-medium">
          {formatCost(estimate.estimated_total_cost || 0)}
        </div>
      </div>
    </div>
  );
}
