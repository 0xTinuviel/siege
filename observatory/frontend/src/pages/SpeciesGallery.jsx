import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { api, useFetch } from '../api';
import ConversationView from '../components/ConversationView';

const STRATEGY_COLORS = {
  authority_intensity: { border: 'border-amber-400/30', accent: 'text-amber-400', bar: 'bg-amber-400/70' },
  social_intensity: { border: 'border-green-700/40', accent: 'text-green-400', bar: 'bg-green-400/70' },
  emotional_intensity: { border: 'border-red-700/40', accent: 'text-red-400', bar: 'bg-red-400/70' },
  technical_intensity: { border: 'border-blue-700/40', accent: 'text-blue-400', bar: 'bg-blue-400/70' },
  policy_intensity: { border: 'border-gray-600', accent: 'text-gray-400', bar: 'bg-gray-400/70' },
  setup_ratio: { border: 'border-amber-400/30', accent: 'text-amber-300', bar: 'bg-amber-300/70' },
  adaptiveness: { border: 'border-gray-600', accent: 'text-gray-300', bar: 'bg-gray-300/70' },
  embedding_density: { border: 'border-blue-700/40', accent: 'text-blue-300', bar: 'bg-blue-300/70' },
  direct: { border: 'border-red-700/40', accent: 'text-red-400', bar: 'bg-red-400/70' },
  unknown: { border: 'border-gray-700', accent: 'text-gray-400', bar: 'bg-gray-400/70' },
};

const BD_LABELS = [
  'Turn Count', 'Setup Ratio', 'Length Var',
  'Authority', 'Social Eng', 'Emotional',
  'Technical', 'Policy', 'Questions',
  'Adaptive', 'Embedding', 'Penetration',
];

export default function SpeciesGallery() {
  const { data: gens } = useFetch(() => api.generations(), []);
  const maxGen = gens && gens.length > 0 ? Math.max(...gens.map(g => g.generation)) : 0;
  const [gen, setGen] = useState(0);

  useEffect(() => { if (gens && maxGen > 0) setGen(maxGen); }, [gens, maxGen]);

  const { data: gallery, loading, error } = useFetch(
    () => gen >= 0 ? api.speciesGallery(gen) : Promise.resolve([]),
    [gen]
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-wide">Species Gallery</h1>
          <p className="text-gray-500 text-sm mt-1">
            Every attacker alive in generation {gen}, profiled and classified by behavioral strategy.
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <label className="text-gray-500 font-medium">Generation</label>
          <input
            type="range" min={0} max={maxGen} value={gen}
            onChange={e => setGen(+e.target.value)}
            className="w-40"
          />
          <span className="font-mono text-gray-200 text-base w-14 text-right">Gen {gen}</span>
        </div>
      </div>

      {loading && <div className="text-gray-500 py-8 text-center">Loading species gallery...</div>}
      {error && <div className="text-red-400 py-8 text-center">Failed to load gallery.</div>}

      {gallery && gallery.length === 0 && !loading && (
        <div className="text-gray-500 py-12 text-center">
          <p className="text-lg">No attack episodes in generation {gen}.</p>
        </div>
      )}

      {gallery && gallery.length > 0 && (
        <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${Math.min(gallery.length, 6)}, 1fr)` }}>
          {gallery.map(group => {
            const colors = STRATEGY_COLORS[group.strategy_key] || STRATEGY_COLORS.unknown;
            return (
              <a
                key={group.strategy_key}
                href={`#strategy-${group.strategy_key}`}
                className={`rounded border ${colors.border} bg-gray-900 p-3 hover:bg-black/[0.03] transition-colors`}
              >
                <div className={`text-sm font-semibold ${colors.accent} mb-1 truncate`}>{group.strategy_name}</div>
                <div className="text-xs text-gray-500">
                  {group.member_count} attacker{group.member_count !== 1 ? 's' : ''}
                </div>
                <div className="flex items-center gap-2 mt-1.5">
                  <div className="flex-1 h-1 bg-gray-800 rounded-full overflow-hidden">
                    <div className={`h-full ${colors.bar} rounded-full`} style={{ width: `${(group.success_rate || 0) * 100}%` }} />
                  </div>
                  <span className="text-xs font-mono text-gray-400">{((group.success_rate || 0) * 100).toFixed(0)}%</span>
                </div>
              </a>
            );
          })}
        </div>
      )}

      <div className="space-y-10">
        {(gallery || []).map(group => (
          <StrategySection key={group.strategy_key} group={group} viewingGen={gen} />
        ))}
      </div>
    </div>
  );
}


function StrategySection({ group, viewingGen }) {
  const colors = STRATEGY_COLORS[group.strategy_key] || STRATEGY_COLORS.unknown;

  return (
    <div id={`strategy-${group.strategy_key}`}>
      <div className={`border ${colors.border} bg-gray-900 rounded-t p-5`}>
        <div className="flex items-start justify-between gap-4 mb-2">
          <div>
            <h2 className={`text-xl font-semibold ${colors.accent}`}>{group.strategy_name}</h2>
            {group.strategy_description && (
              <p className="text-sm text-gray-500 mt-1 max-w-2xl leading-relaxed">{group.strategy_description}</p>
            )}
          </div>
          <div className="flex gap-4 text-sm shrink-0">
            <Stat label="Attackers" value={group.member_count} />
            <Stat label="Wins" value={group.total_wins} color="text-red-400" />
            <Stat label="Blocked" value={group.total_losses} color="text-green-400" />
            <Stat label="Success" value={`${((group.success_rate || 0) * 100).toFixed(0)}%`}
              color={(group.success_rate || 0) > 0.5 ? 'text-red-400' : 'text-green-400'} />
            <Stat label="Avg Age" value={`${(group.avg_age || 0).toFixed(1)} gen`} />
          </div>
        </div>
      </div>

      <div className={`border-x border-b ${colors.border} rounded-b divide-y divide-gray-800/40 overflow-hidden`}>
        {(group.dossiers || []).map((d, i) => (
          <AttackerDossier key={d.attacker_id} dossier={d} viewingGen={viewingGen} colors={colors} defaultExpanded={i === 0} />
        ))}
      </div>
    </div>
  );
}


function AttackerDossier({ dossier, viewingGen, colors, defaultExpanded }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const d = dossier;
  const isSeed = d.lineage_depth === 0;

  return (
    <div>
      <div
        className="px-5 py-4 flex items-center gap-4 cursor-pointer hover:bg-black/[0.04] transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <span className="text-gray-600 text-xs w-4 font-mono">{expanded ? '\u2212' : '+'}</span>

        <div className="flex items-center gap-2 min-w-0 flex-1">
          <Link
            to={`/genome/attacker/${d.attacker_id}`}
            onClick={e => e.stopPropagation()}
            className="text-red-400 hover:underline font-mono text-sm truncate"
          >
            {d.attacker_id}
          </Link>
          {isSeed && <span className="px-1.5 py-0.5 rounded border border-amber-400/40 text-amber-400 text-xs font-mono">SEED</span>}
        </div>

        <div className="flex items-center gap-4 text-xs shrink-0">
          <span className="text-gray-500">
            Born <span className="text-gray-300 font-mono">Gen {d.born_generation}</span>
          </span>
          {d.age > 0 && (
            <span className="text-gray-500">
              Age <span className="text-gray-300 font-mono">{d.age}</span>
            </span>
          )}
          {d.lineage_depth > 0 && (
            <span className="text-gray-500">
              Mutations <span className="text-gray-300 font-mono">{d.lineage_depth}</span>
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 text-xs shrink-0">
          <span className="text-red-400 font-mono">{d.wins}W</span>
          <span className="text-gray-600">/</span>
          <span className="text-green-400 font-mono">{d.losses}L</span>
        </div>

        {d.fitness?.avg_penetration_depth != null && (
          <div className="text-xs text-gray-500 shrink-0">
            Depth <span className="text-gray-300 font-mono">{d.fitness.avg_penetration_depth.toFixed(2)}</span>
          </div>
        )}
      </div>

      {expanded && (
        <div className="px-6 pb-5 space-y-4">
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-gray-900 rounded border border-gray-800 p-4">
              <h4 className="text-xs text-gray-500 uppercase tracking-wider font-mono mb-3">Provenance</h4>
              <div className="space-y-2 text-sm">
                <InfoRow label="Born" value={`Generation ${d.born_generation}`} />
                <InfoRow label="Current gen" value={`Generation ${viewingGen}`} />
                <InfoRow label="Age" value={d.age === 0 ? 'Seed or just born' : `${d.age} generation${d.age > 1 ? 's' : ''}`} />
                <InfoRow label="Mutations deep" value={d.lineage_depth === 0 ? 'Original seed' : `${d.lineage_depth} from seed`} />
                {d.parent_id && (
                  <div className="flex justify-between items-center">
                    <span className="text-gray-500">Parent</span>
                    <Link to={`/genome/attacker/${d.parent_id}`} className="text-red-400 hover:underline font-mono text-xs truncate max-w-[180px]">
                      {d.parent_id}
                    </Link>
                  </div>
                )}
              </div>
            </div>

            <div className="bg-gray-900 rounded border border-gray-800 p-4">
              <h4 className="text-xs text-gray-500 uppercase tracking-wider font-mono mb-3">Combat Record</h4>
              <div className="space-y-2 text-sm">
                <InfoRow label="Battles" value={d.wins + d.losses} />
                <InfoRow label="Breached" value={d.wins} color="text-red-400" />
                <InfoRow label="Blocked" value={d.losses} color="text-green-400" />
                <InfoRow label="Success rate" value={`${((d.success_rate || 0) * 100).toFixed(0)}%`}
                  color={(d.success_rate || 0) > 0.5 ? 'text-red-400' : 'text-green-400'} />
                {d.fitness?.avg_penetration_depth != null && (
                  <InfoRow label="Avg penetration" value={d.fitness.avg_penetration_depth.toFixed(3)} />
                )}
                {d.fitness?.novelty_score != null && (
                  <InfoRow label="Novelty score" value={d.fitness.novelty_score.toFixed(3)} />
                )}
              </div>
            </div>

            <div className="bg-gray-900 rounded border border-gray-800 p-4">
              <h4 className="text-xs text-gray-500 uppercase tracking-wider font-mono mb-3">Behavioral Fingerprint</h4>
              {d.behavior_descriptor && d.behavior_descriptor.length >= 12 ? (
                <div className="space-y-1.5">
                  {BD_LABELS.map((label, i) => {
                    const val = d.behavior_descriptor[i] || 0;
                    const isHigh = val > 0.3;
                    return (
                      <div key={label} className="flex items-center gap-2 text-xs">
                        <span className={`w-20 truncate ${isHigh ? 'text-gray-200' : 'text-gray-500'}`}>{label}</span>
                        <div className="flex-1 h-1 bg-gray-800 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${isHigh ? colors.bar : 'bg-gray-600'}`}
                            style={{ width: `${Math.min(100, val * 100)}%` }}
                          />
                        </div>
                        <span className={`font-mono w-8 text-right ${isHigh ? 'text-gray-200' : 'text-gray-600'}`}>
                          {val.toFixed(2)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-gray-600 text-xs italic">No behavioral data available.</p>
              )}
            </div>
          </div>

          {d.conversation && d.conversation.length > 0 && (
            <div className="border border-gray-800 rounded p-4">
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-xs text-gray-500 uppercase tracking-wider font-mono">
                  {d.best_episode_outcome === 'ATTACK_SUCCEEDED' ? 'Best Attack' : 'Sample Engagement'}
                </h4>
                {d.best_episode_bank && (
                  <span className="text-xs text-gray-500">
                    vs <Link to={`/genome/bank/${d.best_episode_bank}`} className="text-blue-400 hover:underline font-mono">{shortId(d.best_episode_bank)}</Link>
                    {' \u00b7 '}{d.best_episode_turns} turn{d.best_episode_turns !== 1 ? 's' : ''}
                  </span>
                )}
              </div>
              <ConversationView
                conversation={d.conversation}
                outcome={d.best_episode_outcome}
                amount={d.best_episode_amount}
              />
            </div>
          )}

          {d.code_snippet && (
            <details>
              <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-300 font-mono">
                view source code
              </summary>
              <pre className="mt-2 rounded border border-gray-800 p-4 text-xs text-gray-300 font-mono overflow-x-auto whitespace-pre-wrap max-h-[350px] overflow-y-auto">
                {d.code_snippet}
              </pre>
            </details>
          )}
        </div>
      )}
    </div>
  );
}


function Stat({ label, value, color }) {
  return (
    <div className="text-center">
      <div className="text-xs text-gray-500 uppercase tracking-wider font-mono">{label}</div>
      <div className={`text-lg font-semibold ${color || 'text-gray-200'}`}>{value}</div>
    </div>
  );
}

function InfoRow({ label, value, color }) {
  return (
    <div className="flex justify-between items-center gap-2">
      <span className="text-gray-500">{label}</span>
      <span className={`${color || 'text-gray-200'} font-mono text-xs text-right`}>{value}</span>
    </div>
  );
}

function shortId(id) {
  if (!id) return '\u2014';
  if (id.length <= 20) return id;
  return id.slice(0, 18) + '\u2026';
}
