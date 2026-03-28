import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  LineChart, Line, AreaChart, Area, ComposedChart,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, ReferenceLine,
} from 'recharts';
import { api, useFetch } from '../api';
import PathologyAlerts from '../components/PathologyAlerts';

const METRICS_QUERY = [
  'attack_success_rate', 'legitimate_approval_rate',
  'hof_size', 'species_count_banks', 'species_count_attackers',
].join(',');

export default function GenerationOverview() {
  const navigate = useNavigate();
  const { data: gens, loading: gensLoading } = useFetch(() => api.generations(), []);
  const { data: ts, loading: tsLoading } = useFetch(() => api.timeseries(METRICS_QUERY), []);

  if (gensLoading || tsLoading) return <Loading />;
  if (!gens || gens.length === 0 || !ts) return <Empty />;

  const latest = gens[gens.length - 1];
  const prev = gens.length > 1 ? gens[gens.length - 2] : null;

  const chartData = ts.generations.map((g, i) => ({
    gen: g,
    attack_success: ts.series.attack_success_rate?.[i] ?? null,
    defense_rate: ts.series.attack_success_rate?.[i] != null ? 1 - ts.series.attack_success_rate[i] : null,
    legit_approval: ts.series.legitimate_approval_rate?.[i] ?? null,
    hof_size: ts.series.hof_size?.[i] ?? null,
    species_banks: ts.series.species_count_banks?.[i] ?? null,
    species_attackers: ts.series.species_count_attackers?.[i] ?? null,
  }));

  const handleChartClick = (data) => {
    if (data?.activePayload?.[0]?.payload?.gen !== undefined) {
      navigate(`/episodes/${data.activePayload[0].payload.gen}`);
    }
  };

  const atkRate = latest?.attack_success_rate;
  const defRate = atkRate != null ? 1 - atkRate : null;
  const legitRate = latest?.legitimate_approval_rate;

  const delta = (curr, prevVal) => {
    if (curr == null || prevVal == null) return null;
    return curr - prevVal;
  };
  const atkDelta = delta(atkRate, prev?.attack_success_rate);
  const defDelta = atkDelta != null ? -atkDelta : null;
  const legitDelta = delta(legitRate, prev?.legitimate_approval_rate);

  return (
    <div className="space-y-8">
      {/* Title bar */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-black tracking-tight">The Arms Race</h1>
          <p className="text-gray-500 text-sm mt-1">Generation {latest?.generation ?? 0} — click any chart point to browse episodes</p>
        </div>
        <div className="px-4 py-2 rounded-xl bg-gray-900 border border-gray-800">
          <span className="text-xs text-gray-500 uppercase tracking-wider">Hall of Fame</span>
          <div className="text-2xl font-bold text-amber-400 text-center">{latest?.hof_size ?? 0}</div>
        </div>
      </div>

      {/* Opposing force cards */}
      <div className="grid grid-cols-2 gap-6">
        <ForceCard
          side="attack"
          label="Attackers"
          stats={[
            { label: 'Success Rate', value: pct(atkRate), delta: atkDelta, invert: true },
            { label: 'Penetration Depth', value: pct(latest?.avg_penetration_depth), delta: null },
            { label: 'Species', value: latest?.species_count_attackers ?? '—', delta: null, raw: true },
          ]}
        />
        <ForceCard
          side="defend"
          label="Defenders"
          stats={[
            { label: 'Defense Rate', value: pct(defRate), delta: defDelta },
            { label: 'Legit Approval', value: pct(legitRate), delta: legitDelta },
            { label: 'Species', value: latest?.species_count_banks ?? '—', delta: null, raw: true },
          ]}
        />
      </div>

      <PathologyAlerts alerts={latest?.pathology_alerts} />

      {/* Main Arms Race chart */}
      <Section title="Arms Race Timeline" subtitle="Attack success vs defense rate — when one side gains ground, the other adapts">
        <ResponsiveContainer width="100%" height={340}>
          <ComposedChart data={chartData} onClick={handleChartClick} style={{ cursor: 'pointer' }}>
            <defs>
              <linearGradient id="attackGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#a63d3d" stopOpacity={0.25} />
                <stop offset="95%" stopColor="#a63d3d" stopOpacity={0.02} />
              </linearGradient>
              <linearGradient id="defenseGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3d6ea6" stopOpacity={0.25} />
                <stop offset="95%" stopColor="#3d6ea6" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#d9d5cc" />
            <XAxis dataKey="gen" stroke="#9e998f" tick={{ fill: '#5c5850', fontSize: 12 }}
              label={{ value: 'Generation', position: 'insideBottom', offset: -5, fill: '#5c5850' }} />
            <YAxis domain={[0, 1]} stroke="#9e998f" tick={{ fill: '#5c5850', fontSize: 12 }}
              tickFormatter={v => `${(v * 100).toFixed(0)}%`} />
            <Tooltip
              contentStyle={{ backgroundColor: '#f4f1eb', border: '1px solid #c2bdb3', borderRadius: 4, fontSize: 13 }}
              formatter={(v, name) => [`${(v * 100).toFixed(1)}%`, name]}
            />
            <Legend wrapperStyle={{ fontSize: 13 }} />
            <ReferenceLine y={0.5} stroke="#c2bdb3" strokeDasharray="6 4" />
            <Area type="monotone" dataKey="attack_success" name="Attack Success" stroke="#a63d3d"
              fill="url(#attackGrad)" strokeWidth={2.5} dot={false} activeDot={{ r: 5 }} />
            <Area type="monotone" dataKey="defense_rate" name="Defense Rate" stroke="#3d6ea6"
              fill="url(#defenseGrad)" strokeWidth={2.5} dot={false} activeDot={{ r: 5 }} />
            <Line type="monotone" dataKey="legit_approval" name="Legit Approval" stroke="#4a7a4a"
              strokeWidth={1.5} strokeDasharray="5 5" dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </Section>

      {/* Secondary charts */}
      <div className="grid grid-cols-2 gap-6">
        <Section title="Biodiversity" subtitle="How many distinct species survive">
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="atkSpeciesGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#a63d3d" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#a63d3d" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="bankSpeciesGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3d6ea6" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#3d6ea6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#d9d5cc" />
              <XAxis dataKey="gen" stroke="#9e998f" tick={{ fontSize: 11, fill: '#5c5850' }} />
              <YAxis stroke="#9e998f" tick={{ fontSize: 11, fill: '#5c5850' }} allowDecimals={false} />
              <Tooltip contentStyle={{ backgroundColor: '#f4f1eb', border: '1px solid #c2bdb3', borderRadius: 4 }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Area type="monotone" dataKey="species_attackers" name="Attacker Species" stroke="#a63d3d"
                fill="url(#atkSpeciesGrad)" strokeWidth={2} dot={false} />
              <Area type="monotone" dataKey="species_banks" name="Bank Species" stroke="#3d6ea6"
                fill="url(#bankSpeciesGrad)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </Section>

        <Section title="Escalation" subtitle="Hall of Fame growth over time">
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="hofGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#a67a3d" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#a67a3d" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#d9d5cc" />
              <XAxis dataKey="gen" stroke="#9e998f" tick={{ fontSize: 11, fill: '#5c5850' }} />
              <YAxis stroke="#9e998f" tick={{ fontSize: 11, fill: '#5c5850' }} allowDecimals={false} />
              <Tooltip contentStyle={{ backgroundColor: '#f4f1eb', border: '1px solid #c2bdb3', borderRadius: 4 }} />
              <Area type="monotone" dataKey="hof_size" name="Hall of Fame" stroke="#a67a3d"
                fill="url(#hofGrad)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </Section>
      </div>
    </div>
  );
}


function ForceCard({ side, label, stats }) {
  const isAttack = side === 'attack';
  const borderColor = isAttack ? 'border-red-700/40' : 'border-blue-700/40';
  const accentColor = isAttack ? 'text-red-400' : 'text-blue-400';

  return (
    <div className={`rounded border ${borderColor} bg-gray-900 p-5`}>
      <div className="mb-4">
        <span className={`text-lg font-semibold ${accentColor} uppercase tracking-widest`}>{label}</span>
      </div>
      <div className="grid grid-cols-3 gap-4">
        {stats.map(s => (
          <div key={s.label}>
            <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">{s.label}</div>
            <div className={`text-2xl font-bold ${accentColor}`}>{s.value}</div>
            {s.delta != null && (
              <DeltaBadge delta={s.delta} invert={s.invert} />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}


function DeltaBadge({ delta, invert }) {
  if (delta === 0) return <span className="text-xs text-gray-500">unchanged</span>;
  const positive = delta > 0;
  const good = invert ? !positive : positive;
  const color = good ? 'text-green-400' : 'text-red-400';
  const arrow = positive ? '\u2191' : '\u2193';
  return (
    <span className={`text-xs font-medium ${color}`}>
      {arrow} {Math.abs(delta * 100).toFixed(1)}pp
    </span>
  );
}


function Section({ title, subtitle, children }) {
  return (
    <div className="bg-gray-900 rounded border border-gray-800 p-5">
      <div className="mb-4">
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">{title}</h2>
        {subtitle && <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}


function Loading() {
  return (
    <div className="flex items-center justify-center py-20">
      <div className="text-gray-500 text-lg">Loading evolution data...</div>
    </div>
  );
}

function Empty() {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <h2 className="text-xl font-semibold text-gray-300">No evolution data yet</h2>
      <p className="text-gray-500 mt-2 max-w-md">
        Start the evolution loop to generate data, or run the mock data generator
        to preview the dashboard.
      </p>
    </div>
  );
}


function pct(v) {
  if (v == null) return '\u2014';
  return `${(v * 100).toFixed(1)}%`;
}
