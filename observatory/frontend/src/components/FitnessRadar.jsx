import React from 'react';
import { RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ResponsiveContainer } from 'recharts';

export default function FitnessRadar({ fitness, type }) {
  if (!fitness) return null;

  let data;
  if (type === 'bank') {
    data = [
      { axis: 'Defense (Current)', value: fitness.current_defense_rate ?? 0 },
      { axis: 'Defense (Historical)', value: fitness.historical_defense_rate ?? 0 },
      { axis: 'Legit Approval', value: fitness.legitimate_approval_rate ?? 0 },
      { axis: 'Efficiency', value: Math.max(0, 1 - (fitness.avg_llm_calls_per_episode ?? 0) / 10) },
    ];
  } else {
    data = [
      { axis: 'Success Rate', value: fitness.success_rate ?? 0 },
      { axis: 'Extraction', value: Math.min(1, (fitness.total_extracted ?? 0) / 2000) },
      { axis: 'Novelty', value: fitness.novelty_score ?? 0 },
      { axis: 'Stealth', value: fitness.avg_turns_to_success ? Math.max(0, 1 - fitness.avg_turns_to_success / 5) : 0 },
    ];
  }

  const color = type === 'bank' ? '#3d6ea6' : '#a63d3d';

  return (
    <ResponsiveContainer width="100%" height={250}>
      <RadarChart data={data}>
        <PolarGrid stroke="#d9d5cc" />
        <PolarAngleAxis dataKey="axis" tick={{ fill: '#5c5850', fontSize: 11 }} />
        <PolarRadiusAxis domain={[0, 1]} tick={false} axisLine={false} />
        <Radar dataKey="value" stroke={color} fill={color} fillOpacity={0.25} strokeWidth={2} />
      </RadarChart>
    </ResponsiveContainer>
  );
}
