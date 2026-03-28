import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, useFetch } from '../api';
import ConversationView from '../components/ConversationView';

const TYPE_CONFIG = {
  first_blood: { color: 'border-red-700/50', label: 'First Blood' },
  giant_killer: { color: 'border-amber-400/40', label: 'Giant Killer' },
  close_call: { color: 'border-amber-400/40', label: 'Close Call' },
  breakthrough: { color: 'border-green-700/50', label: 'Breakthrough' },
  extinction: { color: 'border-gray-700', label: 'Extinction' },
  escalation: { color: 'border-blue-700/50', label: 'Escalation' },
};

export default function GreatestHits() {
  const { data: hits, loading, error } = useFetch(() => api.greatestHits(), []);

  if (loading) return <div className="text-gray-500 py-8">Loading greatest hits...</div>;
  if (error) return <div className="text-red-400 py-8">Failed to load greatest hits.</div>;
  if (!hits || hits.length === 0) return (
    <div className="text-gray-500 py-12 text-center">
      <p className="text-lg">No greatest hits yet.</p>
      <p className="text-sm mt-2">Greatest hits are auto-curated from evolution data.</p>
    </div>
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-wide">Greatest Hits</h1>
        <p className="text-gray-500 text-sm mt-1">Auto-curated highlights from the evolutionary run.</p>
      </div>

      <div className="space-y-4">
        {hits.map((hit, i) => (
          <HitCard key={i} hit={hit} />
        ))}
      </div>
    </div>
  );
}

function HitCard({ hit }) {
  const [expanded, setExpanded] = useState(false);
  const [episode, setEpisode] = useState(null);
  const cfg = TYPE_CONFIG[hit.type] || TYPE_CONFIG.breakthrough;

  const handleExpand = async () => {
    if (expanded) {
      setExpanded(false);
      return;
    }
    setExpanded(true);
    if (hit.episode_id && !episode) {
      try {
        const ep = await api.episode(hit.episode_id);
        setEpisode(ep);
      } catch {
        setEpisode(null);
      }
    }
  };

  return (
    <div className={`rounded border ${cfg.color} bg-gray-900 overflow-hidden`}>
      <div
        className="p-5 flex gap-4 cursor-pointer hover:bg-black/[0.04] transition-colors"
        onClick={handleExpand}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-1 flex-wrap">
            <span className="font-semibold text-gray-200 text-base">{hit.title}</span>
            <span className="px-2 py-0.5 rounded border border-gray-700 text-xs text-gray-500 font-mono">Gen {hit.generation}</span>
            <span className="text-xs text-gray-500 uppercase tracking-wider">{cfg.label}</span>
          </div>
          {hit.description && <p className="text-sm text-gray-400 mb-2">{hit.description}</p>}
          <div className="flex gap-3 items-center">
            {hit.episode_id && (
              <span className="text-xs text-gray-600 font-mono">
                {expanded ? '\u2212 hide' : '+ show transcript'}
              </span>
            )}
            {hit.episode_id && (
              <Link
                to={`/episodes/${hit.generation}`}
                onClick={e => e.stopPropagation()}
                className="text-xs text-blue-400 hover:underline"
              >
                browse episodes
              </Link>
            )}
            {hit.genome_id && (
              <Link
                to={`/genome/${hit.genome_id.startsWith('bank') ? 'bank' : 'attacker'}/${hit.genome_id}`}
                onClick={e => e.stopPropagation()}
                className="text-xs text-blue-400 hover:underline"
              >
                view genome
              </Link>
            )}
          </div>
        </div>
      </div>

      {expanded && hit.episode_id && (
        <div className="border-t border-gray-800 px-6 py-4">
          {episode ? (
            <ConversationView
              conversation={episode.conversation}
              outcome={episode.outcome}
              amount={episode.amount_transferred}
            />
          ) : (
            <div className="text-gray-600 py-4 text-center">Loading conversation...</div>
          )}
        </div>
      )}
    </div>
  );
}
