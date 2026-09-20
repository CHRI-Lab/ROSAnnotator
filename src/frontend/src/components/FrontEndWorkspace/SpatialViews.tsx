import { useMemo, useState } from 'react';
import { Box, Checkbox, FormControlLabel, MenuItem, Select, Typography } from '@mui/material';
import type { ViewPanelContext } from './viewTypes';
import { boundedSamples, motionBounds, nearestSample } from './spatialData';
import type { Entity, MotionSample, SpatialData, Timed, WrenchSample } from './spatialData';

const fmt = (n: number) => n.toFixed(2);
const vectorText = (v: number[]) => v.map(fmt).join(', ');

function EntityToggles<T extends Timed>({ entities, hidden, toggle }: {
  entities: Entity<T>[]; hidden: Set<string>; toggle: (id: string) => void;
}) {
  return <Box display="flex" flexWrap="wrap" gap={0.5}>
    {entities.map(e => <FormControlLabel key={e.id} sx={{ mr: 1, maxWidth: '100%', overflowWrap: 'anywhere' }}
      control={<Checkbox size="small" checked={!hidden.has(e.id)} onChange={() => toggle(e.id)} sx={{ color: e.color, '&.Mui-checked': { color: e.color } }} />}
      label={<Typography variant="caption">{e.kind === 'robot' ? '▲ ' : e.kind === 'person' ? '● ' : ''}{e.label}{e.frame_id ? ` (${e.frame_id})` : ''}</Typography>} />)}
  </Box>;
}

function useHidden() {
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  return { hidden, toggle: (id: string) => setHidden(previous => {
    const next = new Set(previous); if (next.has(id)) next.delete(id); else next.add(id); return next;
  }) };
}

export function MotionView({ views, played }: ViewPanelContext) {
  const data = views?.motion?.processed_data as unknown as SpatialData<MotionSample>;
  const { hidden, toggle } = useHidden();
  const [mode, setMode] = useState('motion');
  const [trailSeconds, setTrailSeconds] = useState(10);
  const [hover, setHover] = useState('');
  const bounds = useMemo(() => motionBounds(data.entities), [data]);
  const [xmin, xmax, ymin, ymax] = bounds;
  const x = (n: number) => 42 + (n-xmin)/(xmax-xmin)*400;
  const y = (n: number) => 432 - (n-ymin)/(ymax-ymin)*400;
  const visible = data.entities.filter(e => !hidden.has(e.id));
  return <Box p={1}>
    <Box display="flex" flexWrap="wrap" alignItems="center" gap={1}>
      <Select size="small" value={mode} onChange={e => setMode(e.target.value)} inputProps={{ 'aria-label': 'Motion display mode' }}>
        <MenuItem value="motion">Motion view</MenuItem><MenuItem value="summary">Path summary</MenuItem>
      </Select>
      {mode === 'motion' && <Select size="small" value={trailSeconds} onChange={e => setTrailSeconds(Number(e.target.value))} inputProps={{ 'aria-label': 'Trail duration' }}>
        {[5, 10, 30].map(n => <MenuItem key={n} value={n}>{n}s trail</MenuItem>)}
      </Select>}
      <Typography variant="caption">Frame: {data.fixed_frame} · {fmt(played)}s</Typography>
    </Box>
    <EntityToggles entities={data.entities} hidden={hidden} toggle={toggle} />
    <Typography variant="caption" display="block">▲ Robot · ● Person · arrows show heading / velocity (m/s)</Typography>
    <svg viewBox="0 0 480 470" width="100%" style={{ display: 'block', maxHeight: 600 }} role="img" aria-label="Top-down motion and paths">
      <rect x={42} y={32} width={400} height={400} fill="transparent" stroke="currentColor" opacity={0.4} />
      {[0, 1, 2, 3, 4].map(i => <g key={i} fontSize={10} fill="currentColor">
        <path d={`M ${42+i*100} 32 V 432 M 42 ${32+i*100} H 442`} stroke="currentColor" opacity={0.12} />
        <text x={42+i*100} y={448} textAnchor="middle">{fmt(xmin+(xmax-xmin)*i/4)}</text>
        <text x={38} y={435-i*100} textAnchor="end">{fmt(ymin+(ymax-ymin)*i/4)}</text>
      </g>)}
      <text x={242} y={465} fill="currentColor" textAnchor="middle" fontSize={12}>X (m)</text>
      <text x={12} y={20} fill="currentColor" fontSize={12}>Y (m)</text>
      {visible.map(entity => {
        const current = nearestSample(entity.samples, played, data.sample_tolerance_seconds);
        const points = mode === 'summary' ? boundedSamples(entity.samples, 1000)
          : current ? boundedSamples(entity.samples.filter(s => s.seconds <= played && s.seconds >= played-trailSeconds), 250) : [];
        return <g key={entity.id}>
          {points.slice(1).map((s, i) => <line key={s.seconds} x1={x(points[i].position[0])} y1={y(points[i].position[1])}
            x2={x(s.position[0])} y2={y(s.position[1])} stroke={entity.color} strokeWidth={3}
            opacity={mode === 'summary' ? 0.85 : Math.max(0.08, 1-(played-s.seconds)/trailSeconds)} />)}
          {mode === 'motion' && current && (() => {
            const px = x(current.position[0]), py = y(current.position[1]);
            const speed = Math.hypot(current.velocity[0], current.velocity[1]);
            const info = `${entity.label} · t=${fmt(current.seconds)}s · XY=(${fmt(current.position[0])}, ${fmt(current.position[1])}) m · velocity=(${vectorText(current.velocity)}) m/s`;
            const angle = -Math.atan2(current.velocity[1], current.velocity[0])*180/Math.PI;
            const length = Math.min(75, speed*22);
            return <g onMouseEnter={() => setHover(info)} onMouseLeave={() => setHover('')}>
              <title>{info}</title>
              {entity.kind === 'robot'
                ? <path d="M 11 0 L -8 -7 L -8 7 Z" transform={`translate(${px} ${py}) rotate(${-current.heading*180/Math.PI})`} fill={entity.color} stroke="currentColor" />
                : <circle cx={px} cy={py} r={8} fill={entity.color} stroke="currentColor" />}
              <line x1={px} y1={py} x2={px+Math.cos(current.heading)*18} y2={py-Math.sin(current.heading)*18} stroke={entity.color} strokeWidth={2} />
              {speed > 1e-6 && <g transform={`translate(${px} ${py}) rotate(${angle})`} stroke={entity.color} fill={entity.color}>
                <line x1={0} y1={0} x2={length} y2={0} strokeWidth={2} />
                <path d={`M ${length} 0 l -6 -4 v 8 Z`} />
              </g>}
            </g>;
          })()}
        </g>;
      })}
    </svg>
    <Typography variant="caption" display="block" sx={{ minHeight: 36 }}>{hover || (mode === 'motion' ? 'Hover an entity for coordinates and velocity. Entities outside the sample range/tolerance are hidden.' : 'Whole paths; distances use the original XY samples.')}</Typography>
    {mode === 'summary' && visible.map(e => <Typography key={e.id} variant="caption" display="block" sx={{ overflowWrap: 'anywhere' }}>
      {e.label}: {fmt(e.summary?.distance_m || 0)} m · average {fmt(e.summary?.average_speed_mps || 0)} m/s
    </Typography>)}
  </Box>;
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
