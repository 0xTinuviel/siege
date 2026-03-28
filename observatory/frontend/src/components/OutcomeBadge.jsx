import React from 'react';

const STYLES = {
  ATTACK_SUCCEEDED: 'text-red-400 border-red-700/50',
  ATTACK_BLOCKED: 'text-green-400 border-green-700/50',
  LEGITIMATE_APPROVED: 'text-blue-400 border-blue-700/50',
  LEGITIMATE_REJECTED: 'text-amber-400 border-amber-400/40',
};

const SHORT = {
  ATTACK_SUCCEEDED: 'BREACH',
  ATTACK_BLOCKED: 'BLOCKED',
  LEGITIMATE_APPROVED: 'APPROVED',
  LEGITIMATE_REJECTED: 'REJECTED',
};

export default function OutcomeBadge({ outcome }) {
  const style = STYLES[outcome] || 'text-gray-400 border-gray-700';
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-mono uppercase tracking-wider border ${style}`}>
      {SHORT[outcome] || outcome}
    </span>
  );
}
