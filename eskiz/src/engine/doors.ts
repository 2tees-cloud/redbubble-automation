// Двери купе ADS BRAND по чистовому проёму.
// Формулы — таблицы 1, 2 и 3 каталога производителя:
// https://ads-decor.ua/wp-content/uploads/Система-Brand.pdf
//   высота двери S = H − 43; ширина двери L = (перехлёст × n + B) / N,
//   где H, B — высота и ширина проёма, N — число дверей, n — число перехлёстов (N − 1);
//   стекло/зеркало 4 мм: S − 63 × L − вычет; ДСП 10 мм: S − 60 × L − вычет;
//   горизонтальные и разделительные профили: L − вычет;
//   с разделительным профилем наполнение уменьшается на вычет таблицы 3 на каждый разделитель.
import type { Part } from './furniture';

export type Fill = 'mirror' | 'glass' | 'board';
export type ProfileId = '020' | '021' | '022' | '07' | '119' | '117' | '120' | '06' | '119L' | '120L' | '06L';
export type DividerId = '03' | '03L' | '31' | '32';
export type ProfileColor = 'silver' | 'champagne' | 'black' | 'gold' | 'white';

export interface Section {
  fill: Fill;
  /** Желаемая высота наполнения, мм. Пусто — делится поровну с другими «авто». */
  height?: number;
}
export interface DoorDesign {
  sections: Section[];
}
export interface DoorsSpec {
  count: number; // 0 — подобрать автоматически
  profile: ProfileId;
  divider: DividerId;
  color: ProfileColor;
  same: boolean; // все двери одинаковые
  designs: DoorDesign[];
}

// [перехлёст, вычет ширины стекла, вычет ширины ДСП, вычет горизонтальных профилей]
export const profiles: Record<ProfileId, readonly [number, number, number, number]> = {
  '020': [33, 38, 35, 50],
  '021': [28, 32, 29, 45],
  '022': [41, 37, 35, 50],
  '07': [41, 37, 35, 50],
  '119': [26, 37, 35, 50],
  '117': [50, 87, 85, 100],
  '120': [41, 69, 67, 82],
  '06': [32, 51, 49, 64],
  '119L': [26, 40, 37, 52],
  '120L': [40, 39, 37, 50],
  '06L': [32, 51, 49, 64],
};

// Вычет на каждый разделитель: [стекло+стекло, стекло+ДСП, ДСП+ДСП]
export const dividers: Record<DividerId, readonly [number, number, number]> = {
  '03': [4, 2, 1],
  '03L': [4, 2, 1],
  '31': [11, 9, 8],
  '32': [37, 35, 34],
};

export const fillInfo: Record<Fill, { title: string; thickness: number }> = {
  mirror: { title: 'Зеркало', thickness: 4 },
  glass: { title: 'Стекло', thickness: 4 },
  board: { title: 'ДСП', thickness: 10 },
};

export const colorNames: Record<ProfileColor, { title: string; swatch: string }> = {
  silver: { title: 'Серебро', swatch: '#b9c0c4' },
  champagne: { title: 'Шампань', swatch: '#cdb68f' },
  gold: { title: 'Золото', swatch: '#c9a24a' },
  black: { title: 'Чёрный', swatch: '#2e3133' },
  white: { title: 'Белый', swatch: '#eceae4' },
};

export const DOOR = { minW: 500, maxW: 1300, minH: 300, maxH: 3200, heightDeduct: 43 } as const;

export const defaultDoors: DoorsSpec = {
  count: 0,
  profile: '020',
  divider: '03',
  color: 'silver',
  same: true,
  designs: [{ sections: [{ fill: 'mirror' }] }],
};

const r1 = (v: number) => Math.round(v * 10) / 10;
const isGlass = (f: Fill) => f !== 'board';

export function doorWidth(openingWidth: number, count: number, profile: ProfileId) {
  return (profiles[profile][0] * (count - 1) + openingWidth) / count;
}

/** Количества дверей, при которых ширина двери в допуске производителя (500–1300 мм). */
export function validCounts(openingWidth: number, profile: ProfileId) {
  const out: number[] = [];
  for (let n = 2; n <= 8; n++) {
    const l = doorWidth(openingWidth, n, profile);
    if (l >= DOOR.minW && l <= DOOR.maxW) out.push(n);
  }
  return out;
}

/** Удобное число дверей: наименьшее, при котором дверь не шире 1100 мм. */
export function suggestCount(openingWidth: number, profile: ProfileId) {
  const ok = validCounts(openingWidth, profile);
  return ok.find((n) => doorWidth(openingWidth, n, profile) <= 1100) ?? ok[0] ?? 2;
}

/** Вычет торца наполнения у горизонтального профиля: стекло 63/2, ДСП 60/2 (таблица 1). */
const endDeduct = (f: Fill) => (isGlass(f) ? 31.5 : 30);

function dividerDeduct(id: DividerId, a: Fill, b: Fill) {
  const [gg, gb, bb] = dividers[id];
  if (isGlass(a) && isGlass(b)) return gg;
  if (!isGlass(a) && !isGlass(b)) return bb;
  return gb;
}

export interface FillPiece {
  door: number; // 1…N
  section: number; // 1 — верхняя
  fill: Fill;
  height: number;
  width: number;
  thickness: number;
}

export interface DoorsResult {
  errors: string[];
  count: number;
  overlaps: number;
  openingWidth: number;
  openingHeight: number;
  doorWidth: number;
  doorHeight: number;
  horizontal: number; // длина горизонтальных и разделительных профилей
  doors: { index: number; pieces: FillPiece[]; dividers: number }[];
  pieces: FillPiece[];
  profiles: { name: string; length: number; qty: number }[];
  hardware: { name: string; qty: number; unit: string }[];
  area: Record<Fill, number>; // м²
  dividerMeters: number;
  railMeters: number;
}

function sanitize(d: DoorDesign | undefined): Section[] {
  const s = (d?.sections ?? []).filter((x) => x && (x.fill === 'mirror' || x.fill === 'glass' || x.fill === 'board')).slice(0, 6);
  return s.length ? s.map((x) => ({ fill: x.fill, height: Number.isFinite(x.height) && x.height! > 0 ? x.height : undefined })) : [{ fill: 'mirror' }];
}

export function designFor(spec: DoorsSpec, i: number): Section[] {
  return sanitize(spec.same ? spec.designs[0] : spec.designs[i] ?? spec.designs[0]);
}

export function calcDoors(openingWidth: number, openingHeight: number, spec: DoorsSpec, railAllowance = 0): DoorsResult {
  const errors: string[] = [];
  const p = profiles[spec.profile] ?? profiles['020'];
  const [overlap, glassW, boardW, horizW] = p;
  const count = spec.count > 0 ? Math.round(spec.count) : suggestCount(openingWidth, spec.profile);
  const overlaps = count - 1;
  const S = openingHeight - DOOR.heightDeduct;
  const L = (overlap * overlaps + openingWidth) / count;
  if (L < DOOR.minW || L > DOOR.maxW) {
    const ok = validCounts(openingWidth, spec.profile);
    errors.push(`Дверь получается ${Math.round(L)} мм в ширину, а можно 500–1300 мм.${ok.length ? ` Подойдёт дверей: ${ok.join(', ')}.` : ''}`);
  }
  if (S < DOOR.minH || S > DOOR.maxH) errors.push(`Высота двери ${Math.round(S)} мм — допустимо 300–3200 мм (проём 343–3243 мм).`);

  const doors: DoorsResult['doors'] = [];
  for (let i = 0; i < count; i++) {
    const sections = designFor(spec, i);
    let total = S - endDeduct(sections[0].fill) - endDeduct(sections[sections.length - 1].fill);
    for (let k = 1; k < sections.length; k++) total -= dividerDeduct(spec.divider, sections[k - 1].fill, sections[k].fill);
    // Последняя вставка без высоты (или самая последняя) забирает остаток.
    let auto = sections.map((s) => s.height === undefined);
    if (!auto.some(Boolean)) auto = sections.map((_, k) => k === sections.length - 1);
    const fixed = sections.reduce((a, s, k) => a + (auto[k] ? 0 : s.height!), 0);
    const autoCount = auto.filter(Boolean).length;
    const each = (total - fixed) / autoCount;
    if (each < 50) errors.push(`Дверь ${i + 1}: вставкам не хватает высоты — уменьшите заданные размеры (на «авто» остаётся ${Math.round(each)} мм).`);
    const heights = sections.map((s, k) => (auto[k] ? each : s.height!));
    // Округляем до 0,1 мм так, чтобы сумма сошлась точно.
    const rounded = heights.map(r1);
    const lastAuto = auto.lastIndexOf(true);
    rounded[lastAuto] = r1(total - rounded.reduce((a, h, k) => (k === lastAuto ? a : a + h), 0));
    const pieces = sections.map((s, k) => ({
      door: i + 1,
      section: k + 1,
      fill: s.fill,
      height: rounded[k],
      width: r1(L - (isGlass(s.fill) ? glassW : boardW)),
      thickness: fillInfo[s.fill].thickness,
    }));
    doors.push({ index: i + 1, pieces, dividers: sections.length - 1 });
  }

  const pieces = doors.flatMap((d) => d.pieces);
  const horizontal = r1(L - horizW);
  const dividerCount = doors.reduce((a, d) => a + d.dividers, 0);
  const rail = r1(openingWidth - railAllowance);
  const profileName = spec.profile.endsWith('L') ? `LITE ${spec.profile}` : `BRAND ${spec.profile}`;
  const profilesList = [
    { name: 'Верхняя направляющая 104', length: rail, qty: 1 },
    { name: 'Нижняя направляющая 308', length: rail, qty: 1 },
    { name: `Вертикальный профиль ${profileName}`, length: r1(S), qty: 2 * count },
    { name: 'Верхний горизонтальный профиль 02', length: horizontal, qty: count },
    { name: 'Нижний горизонтальный профиль 01', length: horizontal, qty: count },
    { name: `Разделительный профиль ${spec.divider}`, length: horizontal, qty: dividerCount },
  ].filter((x) => x.qty > 0);

  const area = { mirror: 0, glass: 0, board: 0 } as Record<Fill, number>;
  for (const f of pieces) area[f.fill] += (f.height * f.width) / 1e6;
  const glassPerimeter = pieces.filter((f) => isGlass(f.fill)).reduce((a, f) => a + (2 * (f.height + f.width)) / 1000, 0);
  const hardware = [
    { name: 'Ролик нижний', qty: 2 * count, unit: 'шт.' },
    { name: 'Ролик верхний асимметричный', qty: 2 * count, unit: 'шт.' },
    { name: 'Набор крепления №1 (винты сборки)', qty: count, unit: 'компл.' },
    { name: 'Стопор в нижнюю направляющую', qty: count, unit: 'шт.' },
    { name: 'Щётка на вертикальные профили', qty: r1((2 * count * S) / 1000), unit: 'м' },
    { name: 'Уплотнитель для стекла/зеркала 4 мм', qty: r1(glassPerimeter), unit: 'м' },
    { name: 'Плёнка безопасности на зеркало', qty: r1(area.mirror), unit: 'м²' },
  ].filter((h) => h.qty > 0);

  return {
    errors,
    count,
    overlaps,
    openingWidth,
    openingHeight,
    doorWidth: r1(L),
    doorHeight: r1(S),
    horizontal,
    doors,
    pieces,
    profiles: profilesList,
    hardware,
    area,
    dividerMeters: (dividerCount * horizontal) / 1000,
    railMeters: rail / 1000,
  };
}

/** Вставки из ДСП 10 мм — как детали для порезки (идут в файл ВіЯр отдельным материалом). */
export function boardParts(r: DoorsResult): Part[] {
  return r.pieces
    .filter((f) => f.fill === 'board')
    .map((f) => ({
      id: `doors:fill:${f.door}-${f.section}`,
      module: 'Двери купе',
      name: `Дверь ${f.door}, вставка ${f.section}`,
      length: f.height,
      width: f.width,
      cutLength: f.height,
      cutWidth: f.width,
      qty: 1,
      thickness: 10,
      material: 'ДСП 10 мм (вставка купе)',
      edges: [0, 0, 0, 0],
      grain: 'Вдоль длины',
      edgeM: 0,
      signature: '',
      holes: [],
    }));
}

/** Спецификация дверей для цеха и стекольщика (CSV, открывается в Excel). */
export function doorsCsv(r: DoorsResult, spec: DoorsSpec) {
  const cell = (v: unknown) => {
    let s = String(v).replace(/[\r\n]+/g, ' ');
    if (/^[=+\-@\t]/.test(s)) s = "'" + s;
    return '"' + s.replaceAll('"', '""') + '"';
  };
  const rows: unknown[][] = [
    ['Двери купе ADS — спецификация'],
    ['Проём Ш × В, мм', r.openingWidth, r.openingHeight],
    ['Дверей', r.count, 'Перехлёстов', r.overlaps],
    ['Дверь Ш × В, мм', r.doorWidth, r.doorHeight],
    ['Профиль', spec.profile, 'Разделитель', spec.divider, 'Цвет', colorNames[spec.color].title],
    [],
    ['ПРОФИЛИ', 'Длина, мм', 'Кол-во'],
    ...r.profiles.map((p) => [p.name, p.length, p.qty]),
    [],
    ['НАПОЛНЕНИЕ', 'Высота, мм', 'Ширина, мм', 'Толщина, мм'],
    ...r.pieces.map((f) => [`Дверь ${f.door}, вставка ${f.section} (сверху): ${fillInfo[f.fill].title}`, f.height, f.width, f.thickness]),
    [],
    ['ФУРНИТУРА', 'Кол-во', 'Ед.'],
    ...r.hardware.map((h) => [h.name, h.qty, h.unit]),
    [],
    ['Расчёт по таблицам 1–3 каталога ADS BRAND. Проверьте проём в трёх точках по высоте и ширине; берите меньший размер.'],
  ];
  return '﻿' + rows.map((row) => row.map(cell).join(';')).join('\r\n');
}
