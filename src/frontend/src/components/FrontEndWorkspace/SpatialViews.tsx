import { useMemo, useState } from 'react';
import { Box, Checkbox, FormControlLabel, Typography } from '@mui/material';
import type { ViewPanelContext } from './viewTypes';
import { boundedSamples, nearestSample } from './spatialData';
import type { Entity, SpatialData, Timed, WrenchSample } from './spatialData';

const fmt = (n: number) => n.toFixed(2);
const vectorText = (v: number[]) => v.map(fmt).join(', ');

function EntityToggles<T extends Timed>({ entities, hidden, toggle }: {
  entities: Entity<T>[]; hidden: Set<string>; toggle: (id: string) => void;
}) {
  return <Box display="flex" flexWrap="wrap" gap={0.5}>
    {entities.map(e => <FormControlLabel key={e.id} sx={{ mr: 1, maxWidth: '100%', overflowWrap: 'anywhere' }}
      control={<Checkbox size="small" checked={!hidden.has(e.id)} onChange={() => toggle(e.id)} sx={{ color: e.color, '&.Mui-checked': { color: e.color } }} />}
      label={<Typography variant="caption">{e.label}{e.frame_id ? ` (${e.frame_id})` : ''}</Typography>} />)}
  </Box>;
}

function useHidden() {
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  return { hidden, toggle: (id: string) => setHidden(previous => {
    const next = new Set(previous); if (next.has(id)) next.delete(id); else next.add(id); return next;
  }) };
}

export function WrenchView({ views, played, onSeek }: ViewPanelContext) {
  const data = views?.wrench?.processed_data as unknown as SpatialData<WrenchSample>;
  const duration = views?.wrench?.duration || 1;
  const { hidden, toggle } = useHidden();
  const [hoverTime, setHoverTime] = useState<number | null>(null);
  const visible = data.entities.filter(e => !hidden.has(e.id));
  const scales = useMemo(() => (['force', 'torque'] as const).map(key => {
    let min = 0, max = 0;
    data.entities.forEach(e => e.samples.forEach(s => s[key].forEach(v => { min = Math.min(min, v); max = Math.max(max, v); })));
    const margin = Math.max((max-min)*0.1, 0.1);
    return [min-margin, max+margin];
  }), [data]);
  const x = (time: number) => 60 + Math.max(0, Math.min(duration, time))/duration*520;
  const pointerTime = (event: React.MouseEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    return Math.max(0, Math.min(duration, ((event.clientX-box.left)/box.width*610-60)/520*duration));
  };
  return <Box p={1}>
    <EntityToggles entities={data.entities} hidden={hidden} toggle={toggle} />
    <Typography variant="caption">X — solid · Y – – dashed · Z ··· dotted. Click a graph to seek.</Typography>
    {(['force', 'torque'] as const).map((key, chart) => {
      const [min, max] = scales[chart];
      const y = (n: number) => 160-(n-min)/(max-min)*125;
      return <svg key={key} viewBox="0 0 610 200" width="100%" role="img" aria-label={`${key} time series`}
        style={{ display: 'block', cursor: 'crosshair', minHeight: 130 }}
        onMouseMove={e => setHoverTime(pointerTime(e))} onMouseLeave={() => setHoverTime(null)} onClick={e => onSeek(pointerTime(e))}>
        <text x={60} y={18} fill="currentColor" fontSize={13}>{key === 'force' ? 'Force (N)' : 'Torque (N·m)'}</text>
        {[0, 1, 2, 3, 4].map(i => <g key={i} fill="currentColor" fontSize={10}>
          <path d={`M 60 ${35+i*31.25} H 580 M ${60+i*130} 35 V 160`} stroke="currentColor" opacity={0.15} />
          <text x={55} y={39+i*31.25} textAnchor="end">{fmt(max-(max-min)*i/4)}</text>
          <text x={60+i*130} y={178} textAnchor="middle">{fmt(duration*i/4)}</text>
        </g>)}
        <text x={320} y={196} fill="currentColor" textAnchor="middle" fontSize={11}>Time (s)</text>
        {visible.map(e => <g key={e.id}>{[0, 1, 2].map(component => <polyline key={component} fill="none"
          points={boundedSamples(e.samples, 1200).map(s => `${x(s.seconds)},${y(s[key][component])}`).join(' ')}
          stroke={e.color} strokeWidth={1.6} strokeDasharray={['', '6 3', '1 3'][component]} />)}
          {(() => { const s = nearestSample(e.samples, played, data.sample_tolerance_seconds);
            return s && s[key].map((v, i) => <circle key={i} cx={x(s.seconds)} cy={y(v)} r={3} fill={e.color} />); })()}
        </g>)}
        <line x1={x(played)} y1={28} x2={x(played)} y2={160} stroke="#ff5252" strokeWidth={2} />
        <text x={Math.min(x(played)+4, 500)} y={29} fill="#ff5252" fontSize={10}>{fmt(played)}s</text>
        {hoverTime !== null && <line x1={x(hoverTime)} y1={35} x2={x(hoverTime)} y2={160} stroke="currentColor" strokeDasharray="3 3" />}
      </svg>;
    })}
    <Box aria-live="polite" sx={{ minHeight: 44 }}>
      {hoverTime === null ? <Typography variant="caption">Hover for sample timestamp and XYZ values. Each series retains its labeled coordinate frame.</Typography>
        : visible.map(e => { const s = nearestSample(e.samples, hoverTime, Infinity); return s && <Typography key={e.id} variant="caption" display="block" sx={{ overflowWrap: 'anywhere' }}>
          {e.label} · {fmt(s.seconds)}s · Force ({vectorText(s.force)}) N · Torque ({vectorText(s.torque)}) N·m
        </Typography>; })}
    </Box>
  </Box>;
}
