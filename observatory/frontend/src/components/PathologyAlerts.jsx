import React from 'react';

const SEVERITY = {
  DISENGAGEMENT: 'red',
  DIVERSITY: 'red',
  LOSS: 'amber',
  CYCLING: 'amber',
  ECHO: 'amber',
  STAGNATION: 'amber',
};

function getSeverityColor(alert) {
  for (const [keyword, color] of Object.entries(SEVERITY)) {
    if (alert.toUpperCase().includes(keyword)) return color;
  }
  return 'amber';
}

export default function PathologyAlerts({ alerts }) {
  if (!alerts || alerts.length === 0) return null;

  return (
    <div className="space-y-2">
      {alerts.map((alert, i) => {
        const color = getSeverityColor(alert);
        const styles = color === 'red'
          ? 'border-red-700/50 text-red-400'
          : 'border-amber-400/40 text-amber-400';
        return (
          <div key={i} className={`border rounded px-4 py-2 text-sm font-mono ${styles}`}>
            {alert}
          </div>
        );
      })}
    </div>
  );
}
