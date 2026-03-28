import React from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, useFetch } from '../api';
import FitnessRadar from '../components/FitnessRadar';
import OutcomeBadge from '../components/OutcomeBadge';

export default function GenomeInspector({ type: propType }) {
  const { id } = useParams();
  const type = propType || (id?.startsWith('bank') || id?.startsWith('seed_bank') ? 'bank' : 'attacker');

  const fetcher = type === 'bank' ? () => api.bank(id) : () => api.attacker(id);
  const { data, loading, error } = useFetch(fetcher, [id]);

  if (loading) return <div className="text-gray-500 py-8">Loading...</div>;
  if (error || !data) return <div className="text-red-400 py-8">Genome not found: {id}</div>;

  return type === 'bank' ? <BankInspector data={data} /> : <AttackerInspector data={data} />;
}

function formatRule(rule) {
  if (typeof rule === 'string') return rule;
  if (typeof rule === 'object' && rule !== null) {
    const parts = [];
    if (rule.name) parts.push(rule.name);
    if (rule.pattern) parts.push(`pattern: ${rule.pattern}`);
    if (rule.action) parts.push(`action: ${rule.action}`);
    if (rule.message) parts.push(`"${rule.message}"`);
    return parts.join(' \u2014 ') || JSON.stringify(rule);
  }
  return String(rule);
}

function formatRules(rules) {
  if (!rules || !Array.isArray(rules) || rules.length === 0) return 'None';
  return rules.map(formatRule).join('\n');
}

function BankInspector({ data }) {
  const pipeline = data.defense_pipeline || {};
  const stages = [
    { name: 'Pre-Processing Rules', content: formatRules(pipeline.pre_processing_rules) },
    { name: 'Classification Prompt', content: pipeline.classification_prompt || 'None' },
    { name: 'Verification Prompt', content: pipeline.transfer_verification_prompt || 'None' },
    { name: 'Post-Processing Rules', content: formatRules(pipeline.post_processing_rules) },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <h1 className="text-2xl font-semibold tracking-wide">Bank Inspector</h1>
        <span className="px-3 py-1 rounded border border-blue-700/40 text-blue-400 text-sm font-mono">{data.genome_id}</span>
        <span className="text-gray-500 text-sm">Generation {data.generation}</span>
      </div>

      {data.lineage?.length > 0 && (
        <div className="text-sm text-gray-400">
          Parent: <Link to={`/genome/bank/${data.lineage[data.lineage.length - 1]}`} className="text-blue-400 hover:underline">
            {data.lineage[data.lineage.length - 1]}
          </Link>
        </div>
      )}

      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-2 space-y-3">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">Defense Pipeline</h2>
          <div className="bg-gray-900 rounded border border-gray-800 p-4 space-y-1">
            <div className="border-b border-gray-800 pb-3">
              <div className="text-xs text-blue-400 font-mono uppercase tracking-wider mb-1">System Prompt</div>
              <div className="text-sm text-gray-300 whitespace-pre-wrap">{pipeline.system_prompt || 'None'}</div>
            </div>
            {stages.map((stage) => (
              <div key={stage.name} className="border-b border-gray-800 py-3 last:border-b-0">
                <div className="text-xs text-blue-400 font-mono uppercase tracking-wider mb-1">{stage.name}</div>
                <div className="text-sm text-gray-300 whitespace-pre-wrap max-h-40 overflow-y-auto">{stage.content}</div>
              </div>
            ))}
          </div>
          <div className="text-sm text-gray-500">
            Approved recipients: <span className="text-gray-300">{(pipeline.approved_recipients || []).join(', ') || 'None'}</span>
            {pipeline.daily_limit != null && <> {' \u00b7 '}Daily limit: <span className="text-gray-300">${pipeline.daily_limit}</span></>}
          </div>
        </div>

        <div className="space-y-4">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">Fitness</h2>
          <div className="bg-gray-900 rounded border border-gray-800 p-4">
            <FitnessRadar fitness={data.fitness} type="bank" />
            {data.fitness && (
              <div className="mt-3 space-y-1 text-sm">
                <FitnessRow label="Defense (current)" value={data.fitness.current_defense_rate} />
                <FitnessRow label="Defense (historical)" value={data.fitness.historical_defense_rate} />
                <FitnessRow label="Legit approval" value={data.fitness.legitimate_approval_rate} />
                <FitnessRow label="Avg LLM calls" value={data.fitness.avg_llm_calls_per_episode} isRaw />
              </div>
            )}
          </div>
        </div>
      </div>

      <WinLossTable records={data.win_loss} isBank={true} />
    </div>
  );
}

function AttackerInspector({ data }) {
  const dimNames = [
    'Turn count', 'Setup ratio', 'Length variance',
    'Authority intensity', 'Social intensity', 'Emotional intensity',
    'Technical intensity', 'Policy intensity',
    'Question ratio', 'Adaptiveness', 'Embedding density',
    'Penetration depth',
  ];
  const bd = data.behavior_descriptor || [];
  const desc = {};
  dimNames.forEach((name, i) => { desc[name] = bd[i] ?? 0; });

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <h1 className="text-2xl font-semibold tracking-wide">Attacker Inspector</h1>
        <span className="px-3 py-1 rounded border border-red-700/40 text-red-400 text-sm font-mono">{data.genome_id}</span>
        <span className="text-gray-500 text-sm">Generation {data.generation}</span>
      </div>

      {data.lineage?.length > 0 && (
        <div className="text-sm text-gray-400">
          Parent: <Link to={`/genome/attacker/${data.lineage[data.lineage.length - 1]}`} className="text-red-400 hover:underline">
            {data.lineage[data.lineage.length - 1]}
          </Link>
        </div>
      )}

      <div className="flex gap-2 flex-wrap">
        {(data.technique_tags || []).map(t => (
          <span key={t} className="px-2 py-1 border border-red-700/40 rounded text-sm text-red-400 font-mono">{t}</span>
        ))}
      </div>

      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-2 space-y-3">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">Source Code</h2>
          <pre className="bg-gray-900 rounded border border-gray-800 p-4 text-sm text-gray-300 font-mono overflow-x-auto whitespace-pre-wrap max-h-[500px] overflow-y-auto">
            {data.code || 'No source code available'}
          </pre>
        </div>

        <div className="space-y-4">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">Fitness</h2>
          <div className="bg-gray-900 rounded border border-gray-800 p-4">
            <FitnessRadar fitness={data.fitness} type="attacker" />
            {data.fitness && (
              <div className="mt-3 space-y-1 text-sm">
                <FitnessRow label="Success rate" value={data.fitness.success_rate} />
                <FitnessRow label="Total extracted" value={data.fitness.total_extracted} isRaw prefix="$" />
                <FitnessRow label="Novelty" value={data.fitness.novelty_score} />
                <FitnessRow label="Avg turns" value={data.fitness.avg_turns_to_success} isRaw />
                <FitnessRow label="Penetration" value={data.fitness.avg_penetration_depth} />
              </div>
            )}
          </div>

          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">Behavioral Descriptors</h2>
          <div className="bg-gray-900 rounded border border-gray-800 p-4 space-y-2 text-sm">
            {Object.entries(desc).map(([k, v]) => (
              <div key={k} className="flex justify-between items-center gap-2">
                <span className="text-gray-400 text-xs">{k}</span>
                <div className="flex items-center gap-2 flex-1 justify-end">
                  <div className="w-20 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-red-500/70 rounded-full"
                      style={{ width: `${Math.min(100, (typeof v === 'number' ? v : 0) * 100)}%` }}
                    />
                  </div>
                  <span className="text-gray-200 font-mono text-xs w-12 text-right">{typeof v === 'number' ? v.toFixed(3) : v}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <WinLossTable records={data.win_loss} isBank={false} />
    </div>
  );
}

function FitnessRow({ label, value, isRaw, prefix }) {
  if (value == null) return null;
  const display = isRaw ? `${prefix || ''}${typeof value === 'number' ? value.toFixed(2) : value}` : `${(value * 100).toFixed(1)}%`;
  return (
    <div className="flex justify-between">
      <span className="text-gray-400">{label}</span>
      <span className="text-gray-200 font-mono">{display}</span>
    </div>
  );
}

function WinLossTable({ records, isBank }) {
  if (!records || records.length === 0) return null;
  const limited = records.slice(0, 20);

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">Win/Loss Record</h2>
      <div className="bg-gray-900 rounded border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-500 text-xs uppercase">
              <th className="px-4 py-2 text-left">Gen</th>
              <th className="px-4 py-2 text-left">{isBank ? 'Attacker' : 'Bank'}</th>
              <th className="px-4 py-2 text-left">Outcome</th>
              <th className="px-4 py-2 text-left">Turns</th>
            </tr>
          </thead>
          <tbody>
            {limited.map((r, i) => (
              <tr key={i} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                <td className="px-4 py-2 text-gray-400 font-mono">{r.generation}</td>
                <td className="px-4 py-2">
                  {isBank ? (
                    r.attacker_id ? <Link to={`/genome/attacker/${r.attacker_id}`} className="text-red-400 hover:underline">{r.attacker_id}</Link> : '\u2014'
                  ) : (
                    <Link to={`/genome/bank/${r.bank_id}`} className="text-blue-400 hover:underline">{r.bank_id}</Link>
                  )}
                </td>
                <td className="px-4 py-2"><OutcomeBadge outcome={r.outcome} /></td>
                <td className="px-4 py-2 text-gray-400">{r.turn_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
