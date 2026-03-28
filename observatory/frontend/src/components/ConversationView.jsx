import React, { useState } from 'react';

const OUTCOME_STYLES = {
  ATTACK_SUCCEEDED: { border: 'border-red-700', text: 'text-red-400', label: 'BREACH' },
  ATTACK_BLOCKED: { border: 'border-green-700', text: 'text-green-400', label: 'BLOCKED' },
  LEGITIMATE_APPROVED: { border: 'border-blue-700', text: 'text-blue-400', label: 'APPROVED' },
  LEGITIMATE_REJECTED: { border: 'border-amber-400', text: 'text-amber-400', label: 'REJECTED' },
};

export default function ConversationView({ conversation, outcome, amount }) {
  const style = OUTCOME_STYLES[outcome] || OUTCOME_STYLES.ATTACK_BLOCKED;

  const grouped = [];
  let currentTurn = -1;
  for (const msg of conversation || []) {
    if (msg.role === 'attacker' || msg.role === 'user') {
      currentTurn = msg.turn ?? currentTurn + 1;
      grouped.push({ type: 'attacker', turn: currentTurn, content: msg.content });
    } else if (msg.role === 'bank_internal') {
      grouped.push({ type: 'internal', turn: currentTurn, stage: msg.stage, content: msg.content });
    } else if (msg.role === 'bank' || msg.role === 'assistant') {
      grouped.push({ type: 'bank', turn: currentTurn, content: msg.content, action: msg.action });
    }
  }

  if (grouped.length === 0) {
    return <div className="text-gray-600 text-sm italic">No conversation data available.</div>;
  }

  return (
    <div className="space-y-0">
      {grouped.map((msg, i) => (
        <TranscriptEntry key={i} msg={msg} outcome={outcome} isLast={i === grouped.length - 1} />
      ))}
      <div className={`border-t ${style.border} mt-4 pt-3 flex items-center justify-between`}>
        <span className={`text-xs font-mono uppercase tracking-widest ${style.text}`}>
          {style.label}
        </span>
        {amount > 0 && (outcome === 'ATTACK_SUCCEEDED' || outcome === 'LEGITIMATE_APPROVED') && (
          <span className={`text-xs font-mono ${style.text}`}>${amount} transferred</span>
        )}
      </div>
    </div>
  );
}

function TranscriptEntry({ msg, outcome, isLast }) {
  const [showInternal, setShowInternal] = useState(false);

  if (msg.type === 'internal') {
    return (
      <div className="py-1 pl-28">
        <button
          onClick={() => setShowInternal(!showInternal)}
          className="text-xs text-gray-600 hover:text-gray-400 transition-colors cursor-pointer font-mono"
        >
          [{showInternal ? '\u2212' : '+'}] internal / {msg.stage}
        </button>
        {showInternal && (
          <div className="mt-1 text-xs text-gray-500 font-mono whitespace-pre-wrap pl-4 border-l border-gray-800">
            {msg.content}
          </div>
        )}
      </div>
    );
  }

  const isAttacker = msg.type === 'attacker';
  const label = isAttacker ? 'ATTACKER' : 'BANK';
  const labelColor = isAttacker ? 'text-red-400' : 'text-blue-400';

  return (
    <div className={`flex gap-4 py-3 ${!isLast ? 'border-b border-gray-800/60' : ''}`}>
      <div className="w-24 shrink-0 text-right pt-0.5">
        <span className={`text-xs font-mono uppercase tracking-wider ${labelColor}`}>{label}</span>
        <div className="text-xs text-gray-600 font-mono">{msg.turn}</div>
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm text-gray-200 whitespace-pre-wrap leading-relaxed">{msg.content}</div>
        {msg.action && msg.action.type === 'TRANSFER' && (
          <div className={`mt-2 text-xs font-mono ${outcome === 'ATTACK_SUCCEEDED' ? 'text-red-400' : 'text-green-400'}`}>
            TRANSFER \u2192 {msg.action.to} \u2014 ${msg.action.amount}
          </div>
        )}
      </div>
    </div>
  );
}
