// Плоская объёмная картинка (SVG). Нужна для печати/PDF и как запасной вид, если нет 3D.
import { useId, useMemo } from 'react';
import type { Project } from '../engine/furniture';
import { buildScene, type Role } from '../engine/geometry';
import { colorInfo, type Color } from '../engine/order';

type Point = [number, number, number];
type Face = { points: Point[]; tone: number; role: Role };

const woodGrain: Record<Color, boolean> = { white: false, oak: true, walnut: true, graphite: false };
const fixed: Partial<Record<Role, string>> = { mirror: '#c4dce3', metal: '#8a9498', handle: '#6f777b', worktop: '#5a554e' };

function shade(hex: string, factor: number) {
  return '#' + [1, 3, 5].map((i) => Math.min(255, Math.round(parseInt(hex.slice(i, i + 2), 16) * factor)).toString(16).padStart(2, '0')).join('');
}

export default function FurnitureView({ project, color, doors, worktop, angle = 24 }: { project: Project; color: Color; doors: boolean; worktop?: boolean; angle?: number }) {
  const uid = useId().replaceAll(':', '');
  const base = colorInfo[color].swatch;
  const theta = (angle * Math.PI) / 180;
  const phi = 0.16;
  const proj = ([x, y, z]: Point): [number, number] => [
    Math.cos(theta) * x + Math.sin(theta) * z,
    Math.sin(theta) * Math.sin(phi) * x - Math.cos(phi) * y - Math.cos(theta) * Math.sin(phi) * z,
  ];

  const scene = useMemo(() => buildScene(project, { doors, worktop }), [project, doors, worktop]);
  const faces = useMemo(() => {
    const out: Face[] = [];
    for (const b of scene.boxes) {
      const { x, y, z, w, h, d } = b;
      const tone = b.role === 'back' ? 0.78 : b.role === 'plinth' ? 0.7 : 1;
      out.push({ points: [[x, y, z], [x + w, y, z], [x + w, y + h, z], [x, y + h, z]], tone: tone * 1.03, role: b.role });
      out.push({ points: [[x + w, y, z], [x + w, y, z + d], [x + w, y + h, z + d], [x + w, y + h, z]], tone: tone * 0.79, role: b.role });
      out.push({ points: [[x, y + h, z], [x + w, y + h, z], [x + w, y + h, z + d], [x, y + h, z + d]], tone: tone * 1.13, role: b.role });
    }
    return out;
  }, [scene]);

  const pts = faces.flatMap((f) => f.points.map(proj));
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
  const colorOf = (f: Face) => shade(fixed[f.role] ?? base, f.tone);

  return (
    <figure className="view">
      <svg viewBox="0 0 820 540" role="img" aria-label={`Мебель ${scene.width}×${scene.height}×${scene.depth} мм, ${colorInfo[color].title}`}>
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
          points={[floor(0, -20), floor(scene.width + 160, -20), floor(scene.width + 160, scene.depth + 130), floor(0, scene.depth + 130)].join(' ')}
          fill="#4c4639" opacity=".2" filter={`url(#${uid}blur)`}
        />
        <g transform={`translate(${tx} ${ty}) scale(${scale})`}>
          {faces.map((f, i) => {
            const points = f.points.map(proj).map((p) => p.join(',')).join(' ');
            return (
              <g key={i}>
                <polygon points={points} fill={colorOf(f)} stroke={shade(fixed[f.role] ?? base, f.tone * 0.85)} strokeWidth={0.55 / scale} strokeLinejoin="round" />
                {woodGrain[color] && (f.role === 'body' || f.role === 'front') && <polygon points={points} fill={`url(#${uid}grain)`} />}
              </g>
            );
          })}
        </g>
      </svg>
      <figcaption>
        {scene.width} × {scene.height} × {scene.depth} мм
      </figcaption>
    </figure>
  );
}
