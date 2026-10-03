// Расчёт цены по деталировке и прайсу мастера.
// Вся фурнитура подбирается автоматически по правилам ниже.
import { calculate, type Part, type Project } from './furniture';
import { calculateSliding } from './sliding';
import { buildProject, type Facade, type Order, type Tier } from './order';

export type TierPrices = Record<Tier, number>;

export interface PriceList {
  ldspSheet: number; // ЛДСП 18 мм, лист 2800×2070
  hdfSheet: number; // ХДФ 3 мм, лист 2800×2070
  edgePerM: number; // кромка, материал
  cutPerSheet: number; // порезка листа
  edgingPerM: number; // работа по кромкованию
  facadeM2: Record<Exclude<Facade, 'ldsp'>, number>;
  hinge: TierPrices;
  handle: TierPrices;
  leg: TierPrices;
  hanger: TierPrices;
  shelfSupport: TierPrices;
  fastenersPerModule: TierPrices;
  coupeDoor: TierPrices; // профиль + ролики на одну дверь купе
  mirrorM2: number;
  boardFillM2: number;
  worktopPerM: number;
  plinthPerM: number;
  laborPercent: number; // работа цеха, % от материалов
  markupPercent: number; // ваша наценка
  installPercent: number; // монтаж, % от цены изделия
  delivery: number;
  sheetUse: number; // какая часть листа идёт в дело, 0.8 = 20 % отходов
}

export const defaultPrices: PriceList = {
  ldspSheet: 2100,
  hdfSheet: 450,
  edgePerM: 18,
  cutPerSheet: 250,
  edgingPerM: 22,
  facadeM2: { mdf_film: 2800, mdf_paint: 4800, acrylic: 4200 },
  hinge: { eco: 45, standard: 110, premium: 320 },
  handle: { eco: 50, standard: 120, premium: 250 },
  leg: { eco: 20, standard: 35, premium: 70 },
  hanger: { eco: 30, standard: 60, premium: 150 },
  shelfSupport: { eco: 2, standard: 4, premium: 10 },
  fastenersPerModule: { eco: 60, standard: 100, premium: 150 },
  coupeDoor: { eco: 2500, standard: 3800, premium: 6000 },
  mirrorM2: 950,
  boardFillM2: 600,
  worktopPerM: 2200,
  plinthPerM: 350,
  laborPercent: 30,
  markupPercent: 25,
  installPercent: 10,
  delivery: 1000,
  sheetUse: 0.8,
};

const SHEET_M2 = 2.8 * 2.07;

/** Сколько петель нужно двери данной высоты (мм). */
export function hingesFor(doorHeight: number) {
  if (doorHeight <= 900) return 2;
  if (doorHeight <= 1600) return 3;
  if (doorHeight <= 2000) return 4;
  return 5;
}

export type Group = 'Плита и кромка' | 'Фасады' | 'Фурнитура' | 'Кухня' | 'Двери купе' | 'Работа';

export interface Line {
  group: Group;
  name: string;
  qty: number;
  unit: string;
  price: number;
  sum: number;
}

export interface Quote {
  ok: boolean;
  problems: string[];
  warnings: string[];
  project: Project;
  parts: Part[];
  lines: Line[];
  materials: number;
  labor: number;
  product: number; // изделие для клиента: (материалы + работа) × наценка
  install: number;
  delivery: number;
  total: number; // итог клиенту, округлён до 100 грн
  cost: number; // ваша себестоимость: материалы + работа + доставка
  profit: number;
  summary: string[]; // что входит — простыми словами для клиента
}

const role = (p: Part) => p.id.split(':')[1];
const area = (p: Part) => (p.length * p.width) / 1e6;
const r2 = (n: number) => Math.round(n * 100) / 100;

export function calcQuote(order: Order, prices: PriceList = defaultPrices): Quote {
  const project = buildProject(order);
  const { parts, errors, warnings } = calculate(project);
  const lines: Line[] = [];
  const tier = order.hardware;
  const add = (group: Group, name: string, qty: number, unit: string, price: number) => {
    if (qty > 0) lines.push({ group, name, qty: r2(qty), unit, price, sum: Math.round(qty * price) });
  };

  const doors = parts.filter((p) => role(p) === 'door');
  const ldspFronts = order.facade === 'ldsp';
  const bodyParts = parts.filter((p) => role(p) !== 'back' && (role(p) !== 'door' || ldspFronts));
  const backs = parts.filter((p) => role(p) === 'back');

  // Плита: площадь деталей с запасом на отходы, округляем вверх до целых листов.
  const use = Math.min(0.95, Math.max(0.5, prices.sheetUse));
  const ldspSheets = Math.ceil(bodyParts.reduce((a, p) => a + area(p), 0) / (SHEET_M2 * use));
  const hdfSheets = Math.ceil(backs.reduce((a, p) => a + area(p), 0) / (SHEET_M2 * Math.min(0.95, use + 0.1)));
  const edgeM = Math.ceil(bodyParts.reduce((a, p) => a + p.edgeM, 0) * 1.1);
  add('Плита и кромка', 'ЛДСП 18 мм, лист 2800×2070', ldspSheets, 'лист', prices.ldspSheet);
  add('Плита и кромка', 'ХДФ задняя стенка, лист', hdfSheets, 'лист', prices.hdfSheet);
  add('Плита и кромка', 'Порезка', ldspSheets + hdfSheets, 'лист', prices.cutPerSheet);
  add('Плита и кромка', 'Кромка (материал)', edgeM, 'м', prices.edgePerM);
  add('Плита и кромка', 'Кромкование (работа)', edgeM, 'м', prices.edgingPerM);

  if (order.facade !== 'ldsp' && doors.length) {
    const facadeArea = doors.reduce((a, p) => a + area(p), 0);
    const names = { mdf_film: 'Фасады МДФ в плёнке', mdf_paint: 'Фасады МДФ крашеные', acrylic: 'Фасады акрил' } as const;
    add('Фасады', names[order.facade], facadeArea, 'м²', prices.facadeM2[order.facade]);
  }

  // Фурнитура — по количеству дверей, полок и корпусов.
  const hinges = doors.reduce((a, p) => a + hingesFor(p.length), 0);
  const shelves = parts.filter((p) => role(p) === 'shelf').length;
  const kitchenModules = project.modules.filter((m) => m.kitchen);
  const legs = kitchenModules.filter((m) => m.kitchen!.kind !== 'wall').length * 4;
  const hangers = kitchenModules.filter((m) => m.kitchen!.kind === 'wall').length * 2;
  add('Фурнитура', 'Петли', hinges, 'шт.', prices.hinge[tier]);
  add('Фурнитура', 'Ручки', doors.length, 'шт.', prices.handle[tier]);
  add('Фурнитура', 'Полкодержатели', shelves * 4, 'шт.', prices.shelfSupport[tier]);
  add('Фурнитура', 'Ножки регулируемые', legs, 'шт.', prices.leg[tier]);
  add('Фурнитура', 'Навесы для верхних шкафов', hangers, 'шт.', prices.hanger[tier]);
  add('Фурнитура', 'Крепёж, конфирматы, мелочи', project.modules.length, 'корпус', prices.fastenersPerModule[tier]);

  // Купе: система на каждую дверь и заполнение.
  let coupeDoors = 0;
  for (const m of project.modules) {
    if (!m.sliding) continue;
    const s = calculateSliding(m, project.thickness);
    if (s.errors.length) continue;
    coupeDoors += m.sliding.count;
    add('Двери купе', 'Зеркало', s.fills.filter((f) => f.kind === 'mirror').reduce((a, f) => a + (f.width * f.height) / 1e6, 0), 'м²', prices.mirrorM2);
    add('Двери купе', 'Вставка ДСП', s.fills.filter((f) => f.kind === 'board').reduce((a, f) => a + (f.width * f.height) / 1e6, 0), 'м²', prices.boardFillM2);
  }
  add('Двери купе', 'Профиль и ролики (система)', coupeDoors, 'дверь', prices.coupeDoor[tier]);

  if (order.kind === 'kitchen') {
    const lowerM = kitchenModules.filter((m) => m.kitchen!.kind !== 'wall').reduce((a, m) => a + m.width, 0) / 1000;
    const worktopM = kitchenModules.filter((m) => m.kitchen!.kind === 'base' || m.kitchen!.kind === 'sink').reduce((a, m) => a + m.width, 0) / 1000;
    if (order.kitchen.worktop) add('Кухня', 'Столешница', worktopM, 'пог. м', prices.worktopPerM);
    add('Кухня', 'Цоколь', lowerM, 'пог. м', prices.plinthPerM);
  }

  const materials = lines.reduce((a, l) => a + l.sum, 0);
  const labor = Math.round((materials * prices.laborPercent) / 100);
  if (labor > 0) lines.push({ group: 'Работа', name: 'Сборка и упаковка в цехе', qty: 1, unit: '', price: labor, sum: labor });
  const product = Math.round((materials + labor) * (1 + prices.markupPercent / 100));
  const install = order.install ? Math.round((product * prices.installPercent) / 100) : 0;
  const delivery = order.delivery ? Math.round(prices.delivery) : 0;
  const total = Math.ceil((product + install + delivery) / 100) * 100;
  const cost = materials + labor + delivery;

  const summary: string[] = [];
  summary.push(`Корпус из ЛДСП 18 мм${ldspFronts ? '' : ', фасады — ' + { mdf_film: 'МДФ в плёнке', mdf_paint: 'МДФ крашеный', acrylic: 'акрил' }[order.facade as Exclude<Facade, 'ldsp'>]}`);
  if (doors.length) summary.push(`${doors.length} ${plural(doors.length, 'дверь', 'двери', 'дверей')} на ${hinges} ${plural(hinges, 'петле', 'петлях', 'петлях')}`);
  if (coupeDoors) summary.push(`${coupeDoors} ${plural(coupeDoors, 'дверь', 'двери', 'дверей')} купе`);
  if (shelves) summary.push(`${shelves} ${plural(shelves, 'полка', 'полки', 'полок')}`);
  if (order.kind === 'kitchen' && order.kitchen.worktop) summary.push('Столешница');
  summary.push({ eco: 'Фурнитура эконом-класса', standard: 'Фурнитура с доводчиками', premium: 'Фурнитура Blum' }[tier]);
  if (order.delivery) summary.push('Доставка');
  if (order.install) summary.push('Сборка и установка у вас дома');

  return {
    ok: errors.length === 0,
    problems: errors,
    warnings,
    project,
    parts,
    lines,
    materials,
    labor,
    product,
    install,
    delivery,
    total,
    cost,
    profit: total - cost,
    summary,
  };
}

/** Детали для раскроя из ЛДСП и ХДФ. Фасады МДФ и акрил заказываются отдельно. */
export function cuttingParts(order: Order, parts: Part[]) {
  return order.facade === 'ldsp' ? parts : parts.filter((p) => role(p) !== 'door');
}

/** Фасады, которые нужно заказать у фасадчиков (если они не из ДСП). */
export function facadeParts(order: Order, parts: Part[]) {
  return order.facade === 'ldsp' ? [] : parts.filter((p) => role(p) === 'door');
}

export function plural(n: number, one: string, few: string, many: string) {
  const a = Math.abs(n) % 100;
  const b = a % 10;
  if (a > 10 && a < 20) return many;
  if (b > 1 && b < 5) return few;
  if (b === 1) return one;
  return many;
}
