// Выдвижные ящики: фасады, короб из ЛДСП 16 мм, дно из ХДФ, направляющие трёх классов.
// Зазоры направляющих — типовые; перед порезкой сверьте со схемой выбранной модели.
import type { Module, Part, Project } from './furniture';
import type { Tier } from './order';

/** Корпус, в котором вместо дверей и полок — ящики. */
export type DrawerModule = Module & { drawers?: number };

export const slideInfo: Record<Tier, { title: string; clearance: number }> = {
  // clearance — сколько мм занимают две направляющие по ширине (короб = внутренняя ширина − clearance)
  eco: { title: 'роликовые направляющие', clearance: 25 },
  standard: { title: 'шариковые направляющие полного выдвижения', clearance: 26 },
  premium: { title: 'Blum Tandem/Movento скрытого монтажа с доводчиком', clearance: 10 },
};

export const BOX = { side: 16, bottom: 3, minFront: 100, minBox: 60, maxBox: 220 } as const;
const SLIDE_LENGTHS = [550, 500, 450, 400, 350, 300, 250];
const BOX_MATERIAL = 'ЛДСП 16 мм, белый (короба ящиков)';
const BOTTOM_MATERIAL = 'HDF — декор не выбран'; // как у задних стенок: один файл на ХДФ

/** Самая длинная стандартная направляющая, которая помещается в глубину корпуса. */
export function slideLength(depth: number) {
  return SLIDE_LENGTHS.find((l) => l <= depth - 20) ?? 0;
}

/** Сколько ящиков подходит комоду этой высоты. */
export function drawersFor(height: number) {
  return Math.max(2, Math.min(6, Math.round(height / 220)));
}

export interface DrawerLayout {
  errors: string[];
  fronts: { y: number; h: number; w: number; x: number }[];
  box: { x: number; w: number; h: number; length: number };
  parts: Part[];
}

const r1 = (v: number) => Math.round(v * 10) / 10;

function part(id: string, module: string, name: string, length: number, width: number, thickness: number, material: string, edges: [number, number, number, number]): Part {
  const cutLength = r1(length - edges[2] - edges[3]);
  const cutWidth = r1(width - edges[0] - edges[1]);
  const edgeM = r1(((edges[0] > 0 ? length : 0) + (edges[1] > 0 ? length : 0) + (edges[2] > 0 ? width : 0) + (edges[3] > 0 ? width : 0)) / 1000);
  return { id, module, name, length: r1(length), width: r1(width), cutLength, cutWidth, qty: 1, thickness, material, edges, grain: 'Вдоль длины', edgeM, signature: '', holes: [] };
}

export function drawerLayout(m: DrawerModule, project: Project, tier: Tier): DrawerLayout {
  const n = m.drawers ?? 0;
  const t = project.thickness;
  const g = project.gap;
  const e = project.edge;
  const errors: string[] = [];
  const frontH = (m.height - (n + 1) * g) / n;
  const frontW = m.width - 2 * g;
  const inner = m.width - 2 * t;
  const boxW = inner - slideInfo[tier].clearance;
  const length = slideLength(m.depth);
  const boxH = Math.max(BOX.minBox, Math.min(BOX.maxBox, frontH - 50));
  if (frontH < BOX.minFront) errors.push(`${m.name}: слишком много ящиков для такой высоты — фасад ${Math.round(frontH)} мм.`);
  if (!length) errors.push(`${m.name}: глубина ${m.depth} мм мала для направляющих (нужно от 270 мм).`);
  if (boxW < 150) errors.push(`${m.name}: слишком узко для ящика.`);

  const fronts = Array.from({ length: n }, (_, i) => ({ x: g, y: g + i * (frontH + g), w: frontW, h: frontH }));
  const parts: Part[] = [];
  if (!errors.length) {
    // Снизу вверх: «Ящик 1» — нижний.
    fronts.forEach((f, i) => {
      const k = i + 1;
      const name = (s: string) => `Ящик ${k}: ${s}`;
      parts.push(part(`${m.id}:dfront:${k}`, m.name, name('фасад'), f.w, f.h, t, project.material, [e, e, e, e]));
      for (const side of [1, 2]) parts.push(part(`${m.id}:dside:${k}-${side}`, m.name, name(side === 1 ? 'бок левый' : 'бок правый'), length, boxH, BOX.side, BOX_MATERIAL, [e, 0, 0, 0]));
      parts.push(part(`${m.id}:dfb:${k}-1`, m.name, name('лоб короба'), boxW - 2 * BOX.side, boxH, BOX.side, BOX_MATERIAL, [e, 0, 0, 0]));
      parts.push(part(`${m.id}:dfb:${k}-2`, m.name, name('задняя стенка короба'), boxW - 2 * BOX.side, boxH, BOX.side, BOX_MATERIAL, [e, 0, 0, 0]));
      parts.push(part(`${m.id}:dbottom:${k}`, m.name, name('дно'), length, boxW, BOX.bottom, BOTTOM_MATERIAL, [0, 0, 0, 0]));
    });
  }
  return { errors, fronts, box: { x: t + slideInfo[tier].clearance / 2, w: boxW, h: boxH, length }, parts };
}
