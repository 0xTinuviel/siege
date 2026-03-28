import { useState, useEffect } from 'react';

const BASE = '/api';

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  generations: () => fetchJson(`${BASE}/generations`),
  timeseries: (metrics) => fetchJson(`${BASE}/timeseries?metrics=${metrics}`),
  episodes: (gen, params = {}) => {
    const q = new URLSearchParams({ limit: '50', offset: '0', ...params }).toString();
    return fetchJson(`${BASE}/generations/${gen}/episodes?${q}`);
  },
  episode: (id) => fetchJson(`${BASE}/episodes/${id}`),
  bank: (id) => fetchJson(`${BASE}/genomes/banks/${id}`),
  attacker: (id) => fetchJson(`${BASE}/genomes/attackers/${id}`),
  greatestHits: (fromGen = 0, toGen = 999) => fetchJson(`${BASE}/greatest-hits?from_gen=${fromGen}&to_gen=${toGen}`),
  lineageChain: (id) => fetchJson(`${BASE}/lineage/${id}`),
  lineageTree: (type, fromGen = 0, toGen = 999) => {
    const q = new URLSearchParams({ from_gen: fromGen, to_gen: toGen });
    if (type) q.set('type', type);
    return fetchJson(`${BASE}/lineage/tree?${q}`);
  },
  strategyMap: (gen) => fetchJson(`${BASE}/strategy-map/${gen}`),
  diagnostics: (gen) => fetchJson(`${BASE}/diagnostics/${gen}`),
  species: (gen) => fetchJson(`${BASE}/species/${gen}`),
  speciesGallery: (gen) => fetchJson(`${BASE}/species-gallery/${gen}`),
};

export function useFetch(fetcher, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetcher()
      .then(d => { if (!cancelled) { setData(d); setLoading(false); }})
      .catch(e => { if (!cancelled) { setError(e); setLoading(false); }});
    return () => { cancelled = true; };
  }, deps);

  return { data, error, loading };
}
