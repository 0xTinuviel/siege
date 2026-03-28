import React, { useRef, useEffect, useState } from 'react';
import * as d3 from 'd3';
import { api, useFetch } from '../api';

const DIMENSIONS = [
  { key: 'turn_count', label: 'Turn Count' },
  { key: 'setup_ratio', label: 'Setup Ratio' },
  { key: 'length_variance', label: 'Length Variance' },
  { key: 'authority_intensity', label: 'Authority Intensity' },
  { key: 'social_intensity', label: 'Social Engineering' },
  { key: 'emotional_intensity', label: 'Emotional Manipulation' },
  { key: 'technical_intensity', label: 'Technical Exploit' },
  { key: 'policy_intensity', label: 'Policy Manipulation' },
  { key: 'question_ratio', label: 'Question Ratio' },
  { key: 'adaptiveness', label: 'Adaptiveness' },
  { key: 'embedding_density', label: 'Embedding Density' },
  { key: 'penetration_depth', label: 'Penetration Depth' },
  { key: 'success_rate', label: 'Success Rate' },
  { key: 'novelty_score', label: 'Novelty Score' },
];

export default function StrategyMap() {
  const { data: gens } = useFetch(() => api.generations(), []);
  const maxGen = gens && gens.length > 0 ? Math.max(...gens.map(g => g.generation)) : 0;

  const [gen, setGen] = useState(0);
  const [xDim, setXDim] = useState('authority_intensity');
  const [yDim, setYDim] = useState('social_intensity');
  const [playing, setPlaying] = useState(false);
  const svgRef = useRef(null);
  const tooltipRef = useRef(null);
  const intervalRef = useRef(null);

  useEffect(() => { if (gens && maxGen > 0) setGen(maxGen); }, [gens, maxGen]);

  const { data: points, loading, error } = useFetch(() => api.strategyMap(gen), [gen]);

  useEffect(() => {
    if (playing) {
      intervalRef.current = setInterval(() => {
        setGen(prev => {
          if (prev >= maxGen) { setPlaying(false); return maxGen; }
          return prev + 1;
        });
      }, 800);
    }
    return () => clearInterval(intervalRef.current);
  }, [playing, maxGen]);

  useEffect(() => {
    if (!points || !Array.isArray(points) || points.length === 0 || !svgRef.current) return;

    const svg = d3.select(svgRef.current);
    const width = svgRef.current.clientWidth || 800;
    const height = 500;
    const margin = { top: 30, right: 30, bottom: 50, left: 60 };

    svg.attr('viewBox', `0 0 ${width} ${height}`);

    const xValues = points.map(p => p[xDim] ?? 0);
    const yValues = points.map(p => p[yDim] ?? 0);

    const xScale = d3.scaleLinear()
      .domain([Math.min(0, (d3.min(xValues) || 0) - 0.05), Math.max(1, (d3.max(xValues) || 1) + 0.05)])
      .range([margin.left, width - margin.right]);

    const yScale = d3.scaleLinear()
      .domain([Math.min(0, (d3.min(yValues) || 0) - 0.05), Math.max(1, (d3.max(yValues) || 1) + 0.05)])
      .range([height - margin.bottom, margin.top]);

    const colorScale = d3.scaleLinear().domain([0, 0.3, 0.7, 1]).range(['#9e998f', '#a67a3d', '#c25555', '#a63d3d']);
    const sizeScale = d3.scaleLinear().domain([0, 1]).range([5, 18]);

    svg.selectAll('.axis').remove();
    svg.append('g').attr('class', 'axis')
      .attr('transform', `translate(0,${height - margin.bottom})`)
      .call(d3.axisBottom(xScale).ticks(6))
      .selectAll('text').attr('fill', '#5c5850').attr('font-size', '13px');
    svg.append('g').attr('class', 'axis')
      .attr('transform', `translate(${margin.left},0)`)
      .call(d3.axisLeft(yScale).ticks(6))
      .selectAll('text').attr('fill', '#5c5850').attr('font-size', '13px');
    svg.selectAll('.axis line, .axis path').attr('stroke', '#c2bdb3');

    svg.selectAll('.axis-label').remove();
    svg.append('text').attr('class', 'axis-label')
      .attr('x', width / 2).attr('y', height - 6)
      .attr('text-anchor', 'middle').attr('fill', '#5c5850').attr('font-size', 13)
      .text(DIMENSIONS.find(d => d.key === xDim)?.label);
    svg.append('text').attr('class', 'axis-label')
      .attr('transform', `rotate(-90)`).attr('x', -height / 2).attr('y', 14)
      .attr('text-anchor', 'middle').attr('fill', '#5c5850').attr('font-size', 13)
      .text(DIMENSIONS.find(d => d.key === yDim)?.label);

    const circles = svg.selectAll('circle.point').data(points, d => d.genome_id);
    circles.exit().transition().duration(400).attr('r', 0).remove();

    const enter = circles.enter().append('circle').attr('class', 'point')
      .attr('cx', d => xScale(d[xDim] ?? 0))
      .attr('cy', d => yScale(d[yDim] ?? 0))
      .attr('r', 0)
      .attr('fill', d => colorScale(d.success_rate ?? 0))
      .attr('opacity', 0.85)
      .attr('stroke', '#eae7e0')
      .attr('stroke-width', 1.5);

    enter.transition().duration(400).attr('r', d => sizeScale(d.novelty_score ?? 0.3));

    circles.merge(enter).transition().duration(400)
      .attr('cx', d => xScale(d[xDim] ?? 0))
      .attr('cy', d => yScale(d[yDim] ?? 0))
      .attr('r', d => sizeScale(d.novelty_score ?? 0.3))
      .attr('fill', d => colorScale(d.success_rate ?? 0));

    if (!tooltipRef.current) {
      tooltipRef.current = d3.select('body').append('div')
        .attr('class', 'fixed bg-gray-900 text-gray-100 text-sm rounded px-4 py-3 pointer-events-none border border-gray-700 z-50 shadow-md')
        .style('opacity', 0);
    }
    const tooltip = tooltipRef.current;

    svg.selectAll('circle.point')
      .on('mouseover', (e, d) => {
        const tags = (d.technique_tags || []).join(', ') || 'none';
        tooltip.style('opacity', 1)
          .html(`<div class="font-bold mb-1">${d.genome_id}</div>
            <div>Success: ${((d.success_rate ?? 0) * 100).toFixed(1)}%</div>
            <div>Novelty: ${(d.novelty_score ?? 0).toFixed(3)}</div>
            <div class="mt-1 text-gray-500">Tags: ${tags}</div>`)
          .style('left', `${e.pageX + 14}px`)
          .style('top', `${e.pageY - 12}px`);
      })
      .on('mouseout', () => tooltip.style('opacity', 0));

    return () => {
      if (tooltipRef.current) { tooltipRef.current.remove(); tooltipRef.current = null; }
    };
  }, [points, xDim, yDim]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-wide">Strategy Map</h1>
      <p className="text-gray-500 text-sm">
        Each dot is an attacker. Axes show behavioral dimensions. Color encodes success rate. Size encodes novelty score.
      </p>

      <div className="flex items-center gap-6 flex-wrap text-sm">
        <div className="flex items-center gap-2">
          <label className="text-gray-500 font-medium">X axis</label>
          <select value={xDim} onChange={e => setXDim(e.target.value)}
            className="bg-gray-900 border border-gray-700 rounded px-3 py-1.5 text-gray-200 text-sm">
            {DIMENSIONS.map(d => <option key={d.key} value={d.key}>{d.label}</option>)}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-gray-500 font-medium">Y axis</label>
          <select value={yDim} onChange={e => setYDim(e.target.value)}
            className="bg-gray-900 border border-gray-700 rounded px-3 py-1.5 text-gray-200 text-sm">
            {DIMENSIONS.map(d => <option key={d.key} value={d.key}>{d.label}</option>)}
          </select>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={() => setPlaying(!playing)}
            className="px-4 py-1.5 rounded bg-gray-900 border border-gray-700 text-gray-200 hover:border-gray-500 text-sm font-medium transition-colors">
            {playing ? 'Pause' : 'Play'}
          </button>
          <input type="range" min={0} max={maxGen} value={gen} onChange={e => { setPlaying(false); setGen(+e.target.value); }}
            className="w-48" />
          <span className="font-mono text-gray-300 text-base">Gen {gen}</span>
        </div>
      </div>

      {loading && (
        <div className="bg-gray-900 rounded border border-gray-800 flex items-center justify-center h-[500px] text-gray-500">
          Loading strategy map...
        </div>
      )}

      {error && (
        <div className="bg-gray-900 rounded border border-red-700/40 flex items-center justify-center h-[500px] text-red-400">
          Failed to load strategy data for generation {gen}.
        </div>
      )}

      {!loading && !error && (!points || points.length === 0) && (
        <div className="bg-gray-900 rounded border border-gray-800 flex items-center justify-center h-[500px] text-gray-500">
          No attacker data for generation {gen}.
        </div>
      )}

      {!loading && !error && points && points.length > 0 && (
        <div className="bg-gray-900 rounded border border-gray-800 overflow-hidden p-1">
          <svg ref={svgRef} width="100%" height="500" className="w-full" />
        </div>
      )}

      <div className="flex gap-6 text-sm text-gray-500">
        <span>Color: success rate</span>
        <span>Size: novelty score</span>
        <span>{points?.length ?? 0} attackers</span>
      </div>
    </div>
  );
}
