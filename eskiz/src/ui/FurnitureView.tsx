// Объёмная картинка мебели по размерам корпусов. Чистый SVG, без библиотек.
import { useId, useMemo } from 'react';
import type { Project } from '../engine/furniture';
import { frontCount, hasRails, moduleLayout } from '../engine/kitchen';
import { calculateSliding } from '../engine/sliding';
import { colorInfo, type Color } from '../engine/order';

type Point = [number, number, number];
type Role = 'body' | 'front' | 'back' | 'mirror' | 'metal';
type Surface = { points: Point[]; tone: number; role: Role };

const woodGrain: Record<Color, boolean> = { white: false, oak: true, walnut: true, graphite: false };

function shade(hex: string, factor: number) {
  return '#' + [1, 3, 5].map((i) => Math.min(255, Math.round(parseInt(hex.slice(i, i + 2), 16) * factor)).toString(16).padStart(2, '0')).join('');
}

export default function FurnitureView({ project, color, doors, angle = 24 }: { project: Project; color: Color; doors: boolean; angle?: number }) {
  const uid = useId().replaceAll(':', '');
  const base = colorInfo[color].swatch;
  const theta = (angle * Math.PI) / 180;
  const phi = 0.16;
  const proj = ([x, y, z]: Point): [number, number] => [
    Math.cos(theta) * x + Math.sin(theta) * z,
    Math.sin(theta) * Math.sin(phi) * x - Math.cos(phi) * y - Math.cos(theta) * Math.sin(phi) * z,
  ];

  const geometry = useMemo(() => {
    const surfaces: Surface[] = [];
    const layout = moduleLayout(project.modules);
    const t = project.thickness;
    let oy = 0;
    let oz = 0;
    const panel = (x: number, y: number, z: number, w: number, h: number, d: number, tone = 1, role: Role = 'body') => {
      if (w <= 0 || h <= 0 || d <= 0) return;
      y += oy;
      z += oz;
      surfaces.push({ points: [[x, y, z], [x + w, y, z], [x + w, y + h, z], [x, y + h, z]], tone: tone * 1.03, role });
      surfaces.push({ points: [[x + w, y, z], [x + w, y, z + d], [x + w, y + h, z + d], [x + w, y + h, z]], tone: tone * 0.79, role });
      surfaces.push({ points: [[x, y + h, z], [x + w, y + h, z], [x + w, y + h, z + d], [x, y + h, z + d]], tone: tone * 1.13, role });
    };
    for (const item of [...layout.items].sort((a, b) => b.z - a.z || a.x - b.x)) {
      const m = item.m;
      oy = item.y;
      oz = item.z;
      const x = item.x;
      const bay = (m.width - (m.sections + 1) * t) / m.sections;
      const inside = m.height - 2 * t;
      const reserve = m.sliding?.reserve ?? 0;
      if (m.back) panel(x + 1, 1, m.depth, m.width - 2, m.height - 2, 3, 0.78, 'back');
      panel(x, 0, 0, t, m.height, m.depth);
      panel(x + t, 0, 0, m.width - 2 * t, t, m.depth);
      for (let j = 0; j < m.sections; j++) {
        const bx = x + t + j * (bay + t);
        if (j > 0) panel(bx - t, t, reserve, t, inside, m.depth - reserve);
        for (let k = 0; k < m.shelves; k++) {
          panel(bx + 1, t + ((k + 1) * (inside - t)) / (m.shelves + 1), 20 + reserve, bay - 2, t, m.depth - 20 - reserve);
        }
      }
      panel(x + m.width - t, 0, 0, t, m.height, m.depth);
      if (hasRails(m)) {
        const rail = m.kitchen!.railWidth;
        panel(x + t, m.height - t, 0, m.width - 2 * t, t, rail);
        panel(x + t, m.height - t, m.depth - rail, m.width - 2 * t, t, rail);
      } else panel(x + t, m.height - t, 0, m.width - 2 * t, t, m.depth);

      if (doors && m.doors && !m.sliding) {
        const n = frontCount(m);
        const g = project.gap;
        const dw = (m.width - (n + 1) * g) / n;
        for (let j = 0; j < n; j++) panel(x + g + j * (dw + g), g, -t, dw, m.height - 2 * g, t, 1, 'front');
      }
      if (doors && m.sliding) {
        const c = calculateSliding(m, t);
        if (!c.errors.length) {
          panel(x + t, t, 0, c.openingWidth, 10, 58, 1, 'metal');
          panel(x + t, m.height - t - 38, 0, c.openingWidth, 38, 80, 1, 'metal');
          for (const j of [0, 2, 1].filter((j) => j < m.sliding!.count)) {
            const f = c.fills[j];
            const dx = x + t + (j * (c.openingWidth - c.doorWidth)) / (m.sliding.count - 1);
            const dz = j % 2 === 0 ? 38 : 0;
            panel(dx, t + 10, dz, c.doorWidth, c.doorHeight, 8, 1, 'metal');
            panel(dx + 22, t + 50, dz - 1, c.doorWidth - 44, c.doorHeight - 52, 1, 1, f.kind === 'mirror' ? 'mirror' : 'front');
          }
        }
      }
    }
    return { surfaces, width: layout.width, height: layout.height, depth: layout.depth };
  }, [project, doors]);

  const pts = geometry.surfaces.flatMap((f) => f.points.map(proj));
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const scale = Math.min(640 / Math.max(1, maxX - minX), 400 / Math.max(1, maxY - minY));
  const tx = 410 - ((minX + maxX) * scale) / 2;
  const ty = 270 - ((minY + maxY) * scale) / 2;
  const floor = (x: number, z: number) => {
    const p = proj([x, 0, z]);
    return `${p[0] * scale + tx},${p[1] * scale + ty}`;
  };
  const fill = (s: Surface) =>
    s.role === 'mirror' ? shade('#c4dce3', s.tone) : s.role === 'metal' ? shade('#8a9498', s.tone) : shade(base, s.tone);

  return (
    <figure className="view">
      <svg viewBox="0 0 820 540" role="img" aria-label={`Мебель ${geometry.width}×${geometry.height}×${geometry.depth} мм, ${colorInfo[color].title}`}>
        <defs>
          <radialGradient id={uid + 'room'}>
            <stop offset="0" stopColor="var(--view-light)" />
            <stop offset="1" stopColor="var(--view-dark)" />
          </radialGradient>
          <filter id={uid + 'blur'} x="-50%" y="-100%" width="200%" height="300%">
            <feGaussianBlur stdDeviation="12" />
          </filter>
          <pattern id={uid + 'grain'} width="37" height="180" patternUnits="userSpaceOnUse">
            <path d="M3 0 Q12 40 4 90 T5 180 M16 0 Q10 55 19 90 T17 180 M30 0 Q38 80 29 130 L31 180" fill="none" stroke="#473626" strokeWidth=".6" opacity=".13" />
          </pattern>
        </defs>
        <rect width="820" height="540" fill={`url(#${uid}room)`} />
        <polygon
          points={[floor(0, -20), floor(geometry.width + 160, -20), floor(geometry.width + 160, geometry.depth + 130), floor(0, geometry.depth + 130)].join(' ')}
          fill="#4c4639" opacity=".2" filter={`url(#${uid}blur)`}
        />
        <g transform={`translate(${tx} ${ty}) scale(${scale})`}>
          {geometry.surfaces.map((s, i) => {
            const points = s.points.map(proj).map((p) => p.join(',')).join(' ');
            return (
              <g key={i}>
                <polygon points={points} fill={fill(s)} stroke={shade(s.role === 'metal' ? '#8a9498' : base, s.tone * 0.85)} strokeWidth={0.55 / scale} strokeLinejoin="round" />
                {woodGrain[color] && (s.role === 'body' || s.role === 'front') && <polygon points={points} fill={`url(#${uid}grain)`} />}
              </g>
            );
          })}
        </g>
      </svg>
      <figcaption>
        {Math.round(geometry.width)} × {Math.round(geometry.height)} × {Math.round(geometry.depth)} мм
      </figcaption>
    </figure>
  );
}
