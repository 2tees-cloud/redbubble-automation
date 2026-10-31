// Выдвижные ящики: фасады, короб из ЛДСП 18 мм (тот же декор, что и корпус), дно из ХДФ.
// Размер короба зависит от направляющих — их мастер настраивает сам (Настройки → Направляющие):
//   скрытый монтаж (Blum Movento/Tandem, Hettich, GIFF PRIME): короб ВНУТРИ = проём − вычет
//   (Blum: 42), длина = направляющая − 10 (Blum). Боковины 18 мм — с запилом 2 мм по низу;
//   боковой монтаж (шариковые): короб снаружи = проём − вычет (обычно 26), длина = направляющая.
import type { Module, Part, Project } from './furniture';
import type { Tier } from './order';

/** Корпус, в котором вместо дверей и полок — ящики. */
export type DrawerModule = Module & { drawers?: number };

export type Mount = 'side' | 'concealed';

export interface SlideSpec {
  name: string;
  mount: Mount;
  /** Боковой монтаж: вычет из ширины проёма до НАРУЖНОЙ ширины короба. Скрытый: до ВНУТРЕННЕЙ. */
  widthDeduct: number;
  /** Длина короба = длина направляющей − этот вычет. */
  lengthDeduct: number;
}

export const defaultSlides: Record<Tier, SlideSpec> = {
  eco: { name: 'GIFF PRIME скрытого монтажа с доводчиком', mount: 'concealed', widthDeduct: 42, lengthDeduct: 10 },
  standard: { name: 'Hettich скрытого монтажа с доводчиком', mount: 'concealed', widthDeduct: 42, lengthDeduct: 10 },
  premium: { name: 'Blum Movento/Tandem скрытого монтажа', mount: 'concealed', widthDeduct: 42, lengthDeduct: 10 },
};

export const mountInfo: Record<Mount, string> = {
  side: 'Боковой монтаж (шариковые)',
  concealed: 'Скрытый монтаж (под дном)',
};

export const BOX = { bottom: 3, minFront: 100, minBox: 60, maxBox: 220 } as const;
const SLIDE_LENGTHS = [550, 500, 450, 400, 350, 300, 250];
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
  warnings: string[];
  fronts: { y: number; h: number; w: number; x: number }[];
  /** x — отступ короба от наружной стороны корпуса, w — наружная ширина, inner — внутренняя. */
  box: { x: number; w: number; inner: number; h: number; length: number; slide: number; side: number };
  parts: Part[];
}

const r1 = (v: number) => Math.round(v * 10) / 10;

/** Деталь для деталировки, раскроя и файлов ВіЯр. Кромка: [L1, L2, W1, W2]. */
export function makePart(id: string, module: string, name: string, length: number, width: number, thickness: number, material: string, edges: [number, number, number, number]): Part {
  const cutLength = r1(length - edges[2] - edges[3]);
  const cutWidth = r1(width - edges[0] - edges[1]);
  const edgeM = r1(((edges[0] > 0 ? length : 0) + (edges[1] > 0 ? length : 0) + (edges[2] > 0 ? width : 0) + (edges[3] > 0 ? width : 0)) / 1000);
  return { id, module, name, length: r1(length), width: r1(width), cutLength, cutWidth, qty: 1, thickness, material, edges, grain: 'Вдоль длины', edgeM, signature: '', holes: [] };
}

export function drawerLayout(m: DrawerModule, project: Project, slide: SlideSpec = defaultSlides.standard): DrawerLayout {
  const n = m.drawers ?? 0;
  const t = project.thickness;
  const side = t; // боковины короба — из той же ЛДСП 18 мм
  const g = project.gap;
  const e = project.edge;
  const errors: string[] = [];
  const warnings: string[] = [];
  const frontH = (m.height - (n + 1) * g) / n;
  const frontW = m.width - 2 * g;
  const opening = m.width - 2 * t;
  const outer = slide.mount === 'side' ? opening - slide.widthDeduct : opening - slide.widthDeduct + 2 * side;
  const inner = outer - 2 * side;
  const slideL = slideLength(m.depth);
  const length = slideL - slide.lengthDeduct;
  const boxH = Math.max(BOX.minBox, Math.min(BOX.maxBox, frontH - 50));
  if (frontH < BOX.minFront) errors.push(`${m.name}: слишком много ящиков для такой высоты — фасад ${Math.round(frontH)} мм.`);
  if (!slideL) errors.push(`${m.name}: глубина ${m.depth} мм мала для направляющих (нужно от 270 мм).`);
  if (inner < 120) errors.push(`${m.name}: слишком узко для ящика.`);
  if (outer > opening) errors.push(`${m.name}: короб шире проёма — проверьте вычет направляющих в настройках.`);
  if (slide.mount === 'concealed' && side > 16) {
    warnings.push(`${m.name}: боковины ящиков ${side} мм — сделайте запил ${side - 16} мм по низу под скрытые направляющие.`);
  }

  const fronts = Array.from({ length: n }, (_, i) => ({ x: g, y: g + i * (frontH + g), w: frontW, h: frontH }));
  const parts: Part[] = [];
  if (!errors.length) {
    // Снизу вверх: «Ящик 1» — нижний.
    fronts.forEach((f, i) => {
      const k = i + 1;
      const name = (s: string) => `Ящик ${k}: ${s}`;
      parts.push(makePart(`${m.id}:dfront:${k}`, m.name, name('фасад'), f.w, f.h, t, project.material, [e, e, e, e]));
      for (const s of [1, 2]) parts.push(makePart(`${m.id}:dside:${k}-${s}`, m.name, name(s === 1 ? 'бок левый' : 'бок правый'), length, boxH, side, project.material, [e, 0, 0, 0]));
      parts.push(makePart(`${m.id}:dfb:${k}-1`, m.name, name('лоб короба'), inner, boxH, side, project.material, [e, 0, 0, 0]));
      parts.push(makePart(`${m.id}:dfb:${k}-2`, m.name, name('задняя стенка короба'), inner, boxH, side, project.material, [e, 0, 0, 0]));
      parts.push(makePart(`${m.id}:dbottom:${k}`, m.name, name('дно'), length, outer, BOX.bottom, BOTTOM_MATERIAL, [0, 0, 0, 0]));
    });
  }
  return { errors, warnings, fronts, box: { x: t + (opening - outer) / 2, w: outer, inner, h: boxH, length, slide: slideL, side }, parts };
}
