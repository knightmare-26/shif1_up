import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Tabs } from './ui';

type LiveSection = 'overview' | 'monitor';

const SECTIONS: { id: LiveSection; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'monitor', label: 'Live Monitor' },
];

/** Switches between the Live overview and the streaming monitor (two routes, one section). */
const LiveSectionTabs: React.FC<{ active: LiveSection }> = ({ active }) => {
  const navigate = useNavigate();
  return (
    <Tabs
      tabs={SECTIONS}
      active={active}
      onChange={(id) => navigate(id === 'overview' ? '/live' : '/live-monitor')}
      label="Live sections"
      idPrefix="live"
    />
  );
};

export default LiveSectionTabs;
