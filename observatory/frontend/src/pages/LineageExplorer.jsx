import React, { useRef, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as d3 from 'd3';
import { api, useFetch } from '../api';

export default function LineageExplorer() {
  const [genomeType, setGenomeType] = useState('attacker');
  const { data: gens } = useFetch(() => api.generations(), []);
  const maxGen = gens && gens.length > 0 ? Math.max(...gens.map(g => g.generation)) : 0;
  const [genRange, setGenRange] = useState([0, 0]);
  const svgRef = useRef(null);
  const tooltipRef = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (gens && maxGen > 0) setGenRange([Math.max(0, maxGen - 10), maxGen]);
  }, [gens, maxGen]);

  const { data: treeData, loading, error } = useFetch(
    () => api.lineageTree(genomeType, genRange[0], genRange[1]),
    [genomeType, genRange[0], genRange[1]]
  );

  useEffect(() => {
    if (!treeData || !svgRef.current) return;
    const nodes = treeData.nodes || [];
    const edges = treeData.edges || [];
    if (nodes.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const width = svgRef.current.clientWidth || 900;
    const height = 600;
    svg.attr('viewBox', `0 0 ${width} ${height}`);

    const g = svg.append('g');

    const zoom = d3.zoom()
      .scaleExtent([0.2, 4])
      .on('zoom', (e) => g.attr('transform', e.transform));
    svg.call(zoom);

    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    const genSpan = Math.max(genRange[1] - genRange[0], 1);

    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(edges.filter(e => {
        const src = typeof e.source === 'string' ? e.source : e.source?.id;
        const tgt = typeof e.target === 'string' ? e.target : e.target?.id;
        return nodeMap.has(src) && nodeMap.has(tgt);
      })).id(d => d.id).distance(60).strength(0.4))
      .force('charge', d3.forceManyBody().strength(-60))
      .force('x', d3.forceX(width / 2).strength(0.04))
      .force('y', d3.forceY().strength(0.4).y(d => {
        const gen = (d.generation ?? 0) - genRange[0];
        return 40 + gen * (height - 80) / genSpan;
      }));

    const validEdges = edges.filter(e => {
      const src = typeof e.source === 'string' ? e.source : e.source?.id;
      const tgt = typeof e.target === 'string' ? e.target : e.target?.id;
      return nodeMap.has(src) && nodeMap.has(tgt);
    });

    const link = g.append('g')
      .selectAll('line')
      .data(validEdges)
      .enter().append('line')
      .attr('stroke', d => (d.fitness_delta || 0) < 0 ? '#a63d3d' : '#4a7a4a')
      .attr('stroke-width', d => Math.max(1, Math.min(4, Math.abs(d.fitness_delta || 0) * 10)))
      .attr('stroke-dasharray', d => (d.fitness_delta || 0) < 0 ? '4 2' : 'none')
      .attr('stroke-opacity', 0.5);

    const fitnessValue = (d) => {
      const fa = d.fitness_after;
      if (!fa) return 0.5;
      return fa.current_defense_rate ?? fa.success_rate ?? 0.5;
    };

    const colorScale = d3.scaleLinear().domain([0, 0.5, 1]).range(['#a63d3d', '#a67a3d', '#4a7a4a']);

    const node = g.append('g')
      .selectAll('g')
      .data(nodes)
      .enter().append('g')
      .style('cursor', 'pointer')
      .on('click', (_, d) => {
        const prefix = d.genome_type === 'bank' ? 'bank' : 'attacker';
        navigate(`/genome/${prefix}/${d.id}`);
      })
      .call(d3.drag()
        .on('start', (e, d) => { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
        .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
        .on('end', (e, d) => { if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }));

    node.append('circle')
      .attr('r', 7)
      .attr('fill', d => colorScale(fitnessValue(d)))
      .attr('stroke', '#eae7e0')
      .attr('stroke-width', 1.5);

    if (!tooltipRef.current) {
      tooltipRef.current = d3.select('body').append('div')
        .attr('class', 'fixed bg-gray-900 text-gray-100 text-sm rounded px-4 py-3 pointer-events-none border border-gray-700 z-50 shadow-md')
        .style('opacity', 0);
    }
    const tooltip = tooltipRef.current;

    node.on('mouseover', (e, d) => {
      const fv = fitnessValue(d);
      const summary = d.mutation_summary || '';
      tooltip.style('opacity', 1)
        .html(`<div class="font-bold">${d.id}</div>
          <div>Gen ${d.generation ?? '?'} \u00b7 Fitness: ${fv.toFixed(3)}</div>
          ${summary ? `<div class="text-gray-400 mt-1 max-w-[250px]">${summary}</div>` : ''}`)
        .style('left', `${e.pageX + 14}px`)
        .style('top', `${e.pageY - 12}px`);
    }).on('mouseout', () => tooltip.style('opacity', 0));

    simulation.on('tick', () => {
      link.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
      node.attr('transform', d => `translate(${d.x},${d.y})`);
    });

    return () => {
      simulation.stop();
      if (tooltipRef.current) { tooltipRef.current.remove(); tooltipRef.current = null; }
    };
  }, [treeData, navigate, genRange]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-wide">Lineage Explorer</h1>
          <p className="text-gray-500 text-sm mt-1">Click a node to inspect the genome. Drag to rearrange.</p>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <select
            value={genomeType}
            onChange={e => setGenomeType(e.target.value)}
            className="bg-gray-900 border border-gray-700 rounded px-3 py-1.5 text-gray-200"
          >
            <option value="bank">Banks</option>
            <option value="attacker">Attackers</option>
          </select>
          <label className="text-gray-400">Gens:</label>
          <input type="number" value={genRange[0]} min={0} max={genRange[1]}
            onChange={e => setGenRange([Math.max(0, +e.target.value), genRange[1]])}
            className="w-16 bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-gray-200" />
          <span className="text-gray-500">\u2013</span>
          <input type="number" value={genRange[1]} min={genRange[0]}
            onChange={e => setGenRange([genRange[0], +e.target.value])}
            className="w-16 bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-gray-200" />
        </div>
      </div>

      {loading && <div className="text-gray-500 py-8 text-center">Loading lineage graph...</div>}
      {error && <div className="text-red-400 py-8 text-center">Failed to load lineage data. Make sure the server is running.</div>}
      {!loading && !error && treeData && (treeData.nodes || []).length === 0 && (
        <div className="text-gray-500 py-12 text-center">
          <p className="text-lg">No lineage data for this range.</p>
          <p className="text-sm mt-2">Lineage is recorded as genomes mutate. Try widening the generation range.</p>
        </div>
      )}

      <div className="bg-gray-900 rounded border border-gray-800 overflow-hidden">
        <svg ref={svgRef} width="100%" height="600" className="w-full" />
      </div>

      <div className="flex gap-5 text-sm text-gray-500">
        <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-green-400 inline-block" /> High fitness</span>
        <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-amber-400 inline-block" /> Medium</span>
        <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-red-400 inline-block" /> Low fitness</span>
        <span className="flex items-center gap-1.5"><span className="w-6 h-0.5 bg-green-400 inline-block" /> Improved</span>
        <span className="flex items-center gap-1.5">
          <span className="w-6 inline-block" style={{ borderTop: '2px dashed #a63d3d' }} /> Decreased
        </span>
      </div>
    </div>
  );
}
