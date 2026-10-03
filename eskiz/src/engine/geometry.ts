// Мебель как набор прямоугольных панелей — общая основа для 3D и картинки в PDF.
// Координаты в мм: x — вправо, y — вверх от пола, z — вглубь от лицевой стороны (0 — фасад корпуса).
import type { Project } from './furniture';
import { frontCount, hasRails, moduleLayout } from './kitchen';
import { calculateSliding } from './sliding';

export type Role = 'body' | 'back' | 'front' | 'mirror' | 'metal' | 'worktop' | 'plinth' | 'handle';

export interface Box {
  x: number; y: number; z: number;
  w: number; h: number; d: number;
  role: Role;
  /** Распашная дверь: сторона петель. */
  hinge?: 'left' | 'right';
  /** Дверь купе: на сколько мм она уезжает в открытом виде. */
  slide?: number;
  /** Ручка принадлежит двери с этим индексом и двигается вместе с ней. */
  door?: number;
}

export interface Scene {
  boxes: Box[];
  width: number;
  height: number;
  depth: number;
}

export function buildScene(project: Project, opts: { doors?: boolean; worktop?: boolean } = {}): Scene {
  const doors = opts.doors ?? true;
  const boxes: Box[] = [];
  const layout = moduleLayout(project.modules);
  const t = project.thickness;

  for (const item of [...layout.items].sort((a, b) => b.z - a.z || a.x - b.x)) {
    const m = item.m;
    const ox = item.x;
    const oy = item.y;
    const oz = item.z;
    const add = (b: Box) => {
      if (b.w > 0 && b.h > 0 && b.d > 0) boxes.push({ ...b, x: b.x + ox, y: b.y + oy, z: b.z + oz });
      return boxes.length - 1;
    };
    const bay = (m.width - (m.sections + 1) * t) / m.sections;
    const inside = m.height - 2 * t;
    const reserve = m.sliding?.reserve ?? 0;

    // Порядок важен для плоской картинки: сначала дальние детали, потом ближние.
    if (m.back) add({ x: 1, y: 1, z: m.depth, w: m.width - 2, h: m.height - 2, d: 3, role: 'back' });
    add({ x: 0, y: 0, z: 0, w: t, h: m.height, d: m.depth, role: 'body' });
    add({ x: t, y: 0, z: 0, w: m.width - 2 * t, h: t, d: m.depth, role: 'body' });
    for (let j = 0; j < m.sections; j++) {
      const bx = t + j * (bay + t);
      if (j > 0) add({ x: bx - t, y: t, z: reserve, w: t, h: inside, d: m.depth - reserve, role: 'body' });
      for (let k = 0; k < m.shelves; k++) {
        const y = t + ((k + 1) * (inside - t)) / (m.shelves + 1);
        add({ x: bx + 1, y, z: 20 + reserve, w: bay - 2, h: t, d: m.depth - 20 - reserve, role: 'body' });
      }
    }
    add({ x: m.width - t, y: 0, z: 0, w: t, h: m.height, d: m.depth, role: 'body' });
    if (hasRails(m)) {
      const rail = m.kitchen!.railWidth;
      add({ x: t, y: m.height - t, z: 0, w: m.width - 2 * t, h: t, d: rail, role: 'body' });
      add({ x: t, y: m.height - t, z: m.depth - rail, w: m.width - 2 * t, h: t, d: rail, role: 'body' });
    } else add({ x: t, y: m.height - t, z: 0, w: m.width - 2 * t, h: t, d: m.depth, role: 'body' });

    // Кухня: цоколь под нижними шкафами и столешница сверху.
    const kind = m.kitchen?.kind;
    if (kind && kind !== 'wall' && oy > 0) add({ x: 0, y: -oy, z: 50, w: m.width, h: oy - 2, d: 16, role: 'plinth' });
    if (opts.worktop && (kind === 'base' || kind === 'sink')) add({ x: 0, y: m.height, z: -t - 22, w: m.width, h: 38, d: m.depth + t + 22, role: 'worktop' });

    if (doors && m.doors && !m.sliding) {
      const n = frontCount(m);
      const g = project.gap;
      const dw = (m.width - (n + 1) * g) / n;
      const dh = m.height - 2 * g;
      for (let j = 0; j < n; j++) {
        // Пары дверей открываются «от центра»: левая — на левых петлях, правая — на правых.
        // Непарная последняя дверь — на правых петлях, чтобы не задевать соседку.
        const hinge: 'left' | 'right' = n === 1 ? 'left' : j % 2 === 1 || j === n - 1 ? 'right' : 'left';
        const x = g + j * (dw + g);
        const idx = add({ x, y: g, z: -t, w: dw, h: dh, d: t, role: 'front', hinge });
        // Ручка у свободного края; у верхних шкафов — внизу, у остальных — на удобной высоте.
        const hx = hinge === 'left' ? x + dw - 40 : x + 28;
        const hh = Math.min(160, dh * 0.3);
        const hy = kind === 'wall' ? g + 40 : hasRails(m) ? g + dh - hh - 40 : g + Math.max(40, Math.min(dh / 2, 1050 - oy)) - hh / 2;
        add({ x: hx, y: hy, z: -t - 26, w: 12, h: hh, d: 26, role: 'handle', door: idx });
      }
    }

    if (doors && m.sliding) {
      const c = calculateSliding(m, t);
      if (!c.errors.length) {
        add({ x: t, y: t, z: 0, w: c.openingWidth, h: 10, d: 58, role: 'metal' });
        add({ x: t, y: m.height - t - 38, z: 0, w: c.openingWidth, h: 38, d: 80, role: 'metal' });
        const count = m.sliding.count;
        // Сначала задние двери (нечётные), потом передние.
        for (const j of [1, 0, 2].filter((j) => j < count)) {
          const f = c.fills[j];
          const dx = t + (j * (c.openingWidth - c.doorWidth)) / (count - 1);
          const dz = j % 2 === 0 ? 0 : 38;
          // В открытом виде крайняя левая дверь уезжает за соседнюю.
          const slide = j === 0 ? c.doorWidth * 0.9 : 0;
          const frame = add({ x: dx, y: t + 10, z: dz, w: c.doorWidth, h: c.doorHeight, d: 30, role: 'metal', slide });
          add({ x: dx + 22, y: t + 50, z: dz - 1, w: c.doorWidth - 44, h: c.doorHeight - 80, d: 10, role: f.kind === 'mirror' ? 'mirror' : 'front', slide, door: frame });
        }
      }
    }
  }

  const xs = boxes.flatMap((b) => [b.x, b.x + b.w]);
  const ys = boxes.flatMap((b) => [b.y, b.y + b.h]);
  return {
    boxes,
    width: Math.round(Math.max(0, ...xs) - Math.min(0, ...xs)),
    height: Math.round(Math.max(0, ...ys)),
    depth: layout.depth,
  };
}
