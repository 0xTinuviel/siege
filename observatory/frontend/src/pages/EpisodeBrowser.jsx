import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, useFetch } from '../api';
import OutcomeBadge from '../components/OutcomeBadge';
import ConversationView from '../components/ConversationView';

const OUTCOMES = ['ATTACK_SUCCEEDED', 'ATTACK_BLOCKED', 'LEGITIMATE_APPROVED', 'LEGITIMATE_REJECTED'];

export default function EpisodeBrowser() {
  const { gen: paramGen } = useParams();
  const { data: gens } = useFetch(() => api.generations(), []);

  const maxGen = gens && gens.length > 0 ? Math.max(...gens.map(g => g.generation)) : 0;
  const [selectedGen, setSelectedGen] = useState(paramGen ? parseInt(paramGen) : null);
  const [outcomeFilter, setOutcomeFilter] = useState(new Set());
  const [techniqueFilter, setTechniqueFilter] = useState('');
  const [expandedEp, setExpandedEp] = useState(null);
  const [fullEpisode, setFullEpisode] = useState(null);
  const [offset, setOffset] = useState(0);

  const gen = selectedGen ?? maxGen;

  useEffect(() => {
    if (paramGen) setSelectedGen(parseInt(paramGen));
  }, [paramGen]);

  const params = {};
  if (outcomeFilter.size === 1) params.outcome = [...outcomeFilter][0];
  if (techniqueFilter) params.technique = techniqueFilter;
  params.offset = String(offset);

  const { data: episodeData, loading } = useFetch(
    () => api.episodes(gen, params),
    [gen, JSON.stringify(params)]
  );

  const episodes = episodeData?.episodes || [];
  const total = episodeData?.total || 0;

  const handleExpand = async (epId) => {
    if (expandedEp === epId) {
      setExpandedEp(null);
      setFullEpisode(null);
      return;
    }
    setExpandedEp(epId);
    try {
      const full = await api.episode(epId);
      setFullEpisode(full);
    } catch {
      setFullEpisode(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-wide">Episode Browser</h1>
        <div className="flex items-center gap-3 text-sm">
          <label className="text-gray-400">Generation:</label>
          <input
            type="range" min={0} max={maxGen} value={gen}
            onChange={e => { setSelectedGen(parseInt(e.target.value)); setOffset(0); }}
            className="w-40"
          />
          <span className="font-mono text-gray-200 w-8 text-right">{gen}</span>
        </div>
      </div>

      <div className="flex gap-4 flex-wrap items-center">
        <div className="flex gap-1">
          {OUTCOMES.map(o => (
            <button
              key={o}
              onClick={() => {
                const next = new Set(outcomeFilter);
                next.has(o) ? next.delete(o) : next.add(o);
                setOutcomeFilter(next);
                setOffset(0);
              }}
              className={`px-2 py-1 rounded text-xs border transition-colors ${
                outcomeFilter.has(o) ? 'bg-gray-800 border-gray-600 text-gray-200' : 'bg-gray-900 border-gray-700 text-gray-500 hover:text-gray-300'
              }`}
            >
              {o.replace('ATTACK_', '').replace('LEGITIMATE_', '')}
            </button>
          ))}
        </div>
        <input
          type="text" placeholder="Filter by technique..."
          value={techniqueFilter} onChange={e => { setTechniqueFilter(e.target.value); setOffset(0); }}
          className="bg-gray-900 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-200 placeholder-gray-600 w-48"
        />
        <span className="text-sm text-gray-500">{total} episodes</span>
      </div>

      <div className="bg-gray-900 rounded border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-500 text-xs uppercase tracking-wider">
              <th className="px-4 py-3 text-left">Gen</th>
              <th className="px-4 py-3 text-left">Bank</th>
              <th className="px-4 py-3 text-left">Attacker</th>
              <th className="px-4 py-3 text-left">Type</th>
              <th className="px-4 py-3 text-left">Outcome</th>
              <th className="px-4 py-3 text-left">Turns</th>
              <th className="px-4 py-3 text-left">Techniques</th>
              <th className="px-4 py-3 text-right">Amount</th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-600">Loading...</td></tr>}
            {!loading && episodes.length === 0 && (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-600">No episodes found for this generation and filter.</td></tr>
            )}
            {!loading && episodes.map(ep => (
              <React.Fragment key={ep.episode_id}>
                <tr
                  onClick={() => handleExpand(ep.episode_id)}
                  className="border-b border-gray-800/50 hover:bg-gray-800/50 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-2.5 font-mono text-gray-400">{ep.generation}</td>
                  <td className="px-4 py-2.5">
                    <Link to={`/genome/bank/${ep.bank_id}`} onClick={e => e.stopPropagation()} className="text-blue-400 hover:underline font-mono text-xs">{shortId(ep.bank_id)}</Link>
                  </td>
                  <td className="px-4 py-2.5">
                    {ep.attacker_id ? (
                      <Link to={`/genome/attacker/${ep.attacker_id}`} onClick={e => e.stopPropagation()} className="text-red-400 hover:underline font-mono text-xs">{shortId(ep.attacker_id)}</Link>
                    ) : <span className="text-gray-600">\u2014</span>}
                  </td>
                  <td className="px-4 py-2.5 text-gray-400">{ep.type}</td>
                  <td className="px-4 py-2.5"><OutcomeBadge outcome={ep.outcome} /></td>
                  <td className="px-4 py-2.5 text-gray-400">{ep.turn_count}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex gap-1 flex-wrap">
                      {(ep.attack_technique_tags || []).map(t => (
                        <span key={t} className="px-1.5 py-0.5 bg-gray-800 rounded text-xs text-gray-400">{t}</span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-gray-400">
                    {ep.amount_transferred > 0 ? `$${ep.amount_transferred}` : '\u2014'}
                  </td>
                </tr>
                {expandedEp === ep.episode_id && (
                  <tr>
                    <td colSpan={8} className="px-6 py-4 bg-gray-950 border-b border-gray-800">
                      {fullEpisode ? (
                        <ConversationView
                          conversation={fullEpisode.conversation}
                          outcome={fullEpisode.outcome}
                          amount={fullEpisode.amount_transferred}
                        />
                      ) : (
                        <div className="text-gray-600 py-4">Loading conversation...</div>
                      )}
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {total > 50 && (
        <div className="flex gap-3 justify-center">
          <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}
            className="px-3 py-1.5 rounded text-sm bg-gray-800 text-gray-300 disabled:opacity-30 hover:bg-gray-700">
            Previous
          </button>
          <span className="text-sm text-gray-500 py-1.5">{offset + 1}\u2013{Math.min(offset + 50, total)} of {total}</span>
          <button disabled={offset + 50 >= total} onClick={() => setOffset(offset + 50)}
            className="px-3 py-1.5 rounded text-sm bg-gray-800 text-gray-300 disabled:opacity-30 hover:bg-gray-700">
            Next
          </button>
        </div>
      )}
    </div>
  );
}

function shortId(id) {
  if (!id) return '\u2014';
  if (id.length <= 20) return id;
  return id.slice(0, 18) + '\u2026';
}
