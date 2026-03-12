import { formatNumber, formatCost } from '../utils/formatters';

export default function TokenCounter({ tokensUsed, costUsd, tokensLimit, budgetLimit }) {
  const tokenPercent = tokensLimit ? (tokensUsed / tokensLimit) * 100 : 0;
  const budgetPercent = budgetLimit ? (costUsd / budgetLimit) * 100 : 0;

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <h3 className="text-sm font-medium text-gray-500 mb-3">Token Usage</h3>
      <div className="space-y-3">
        <div>
          <div className="flex justify-between text-sm">
            <span>Tokens</span>
            <span className="font-mono">
              {formatNumber(tokensUsed)}
              {tokensLimit ? ` / ${formatNumber(tokensLimit)}` : ''}
            </span>
          </div>
          {tokensLimit > 0 && (
            <div className="w-full bg-gray-200 rounded-full h-1.5 mt-1">
              <div
                className={`h-1.5 rounded-full ${tokenPercent > 90 ? 'bg-red-500' : tokenPercent > 70 ? 'bg-yellow-500' : 'bg-blue-500'}`}
                style={{ width: `${Math.min(100, tokenPercent)}%` }}
              />
            </div>
          )}
        </div>
        <div>
          <div className="flex justify-between text-sm">
            <span>Cost</span>
            <span className="font-mono">
              {formatCost(costUsd)}
              {budgetLimit ? ` / ${formatCost(budgetLimit)}` : ''}
            </span>
          </div>
          {budgetLimit > 0 && (
            <div className="w-full bg-gray-200 rounded-full h-1.5 mt-1">
              <div
                className={`h-1.5 rounded-full ${budgetPercent > 90 ? 'bg-red-500' : budgetPercent > 70 ? 'bg-yellow-500' : 'bg-green-500'}`}
                style={{ width: `${Math.min(100, budgetPercent)}%` }}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
