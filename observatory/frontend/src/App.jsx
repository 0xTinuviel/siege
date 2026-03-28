import React from 'react';
import { Routes, Route, Link, useLocation } from 'react-router-dom';
import GenerationOverview from './pages/GenerationOverview';
import EpisodeBrowser from './pages/EpisodeBrowser';
import GenomeInspector from './pages/GenomeInspector';
import GreatestHits from './pages/GreatestHits';
import LineageExplorer from './pages/LineageExplorer';
import StrategyMap from './pages/StrategyMap';
import SpeciesGallery from './pages/SpeciesGallery';

const NAV_ITEMS = [
  { path: '/', label: 'Arms Race' },
  { path: '/episodes', label: 'Episodes' },
  { path: '/species', label: 'Species' },
  { path: '/greatest-hits', label: 'Greatest Hits' },
  { path: '/lineage', label: 'Lineage' },
  { path: '/strategy-map', label: 'Strategy Map' },
];

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error) {
    return { error };
  }
  render() {
    if (this.state.error) {
      return (
        <div className="py-16 text-center">
          <div className="text-red-400 text-lg mb-2 font-medium">Something went wrong</div>
          <div className="text-gray-500 text-sm mb-6 font-mono">{this.state.error.message}</div>
          <button
            onClick={() => this.setState({ error: null })}
            className="px-5 py-2 border border-gray-700 text-gray-400 rounded hover:border-gray-500 hover:text-gray-300 transition-colors text-sm"
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

function NavBar() {
  const location = useLocation();
  return (
    <nav className="border-b border-gray-800 px-6 py-5 flex flex-col items-center gap-4">
      <Link to="/" className="text-2xl font-semibold tracking-wide text-gray-200">
        SIEGE
        <span className="text-gray-500 font-normal ml-2 text-lg">Observatory</span>
      </Link>
      <div className="flex gap-1 justify-center flex-wrap">
        {NAV_ITEMS.map(({ path, label }) => {
          const active = path === '/' ? location.pathname === '/' : location.pathname.startsWith(path);
          return (
            <Link
              key={path}
              to={path}
              className={`px-4 py-1.5 text-base transition-colors ${
                active
                  ? 'text-gray-100 border-b-2 border-gray-400'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              {label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

export default function App() {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <NavBar />
      <main className="px-6 py-8 max-w-[1600px] mx-auto">
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<GenerationOverview />} />
            <Route path="/episodes" element={<EpisodeBrowser />} />
            <Route path="/episodes/:gen" element={<EpisodeBrowser />} />
            <Route path="/genome/bank/:id" element={<GenomeInspector type="bank" />} />
            <Route path="/genome/attacker/:id" element={<GenomeInspector type="attacker" />} />
            <Route path="/greatest-hits" element={<GreatestHits />} />
            <Route path="/lineage" element={<LineageExplorer />} />
            <Route path="/strategy-map" element={<StrategyMap />} />
            <Route path="/species" element={<SpeciesGallery />} />
          </Routes>
        </ErrorBoundary>
      </main>
    </div>
  );
}
