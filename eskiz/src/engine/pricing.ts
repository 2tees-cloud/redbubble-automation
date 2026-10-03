// Расчёт цены по деталировке и прайсу мастера.
// Вся фурнитура подбирается автоматически по правилам ниже.
import { calculate, type Part, type Project } from './furniture';
import { boardParts, calcDoors, colorNames, fillInfo, type DoorsResult } from './doors';
import { buildScene, nicheScene, type Scene } from './geometry';
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
  coupeDoor: TierPrices; // на одну дверь купе: профили, ролики, крепёж, щётка, уплотнитель
  railsPerM: number; // направляющие верх + низ, за погонный метр проёма
  dividerPerM: number; // разделительный профиль
  mirrorM2: number;
  glassM2: number;
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
  railsPerM: 500,
  dividerPerM: 180,
  mirrorM2: 950,
  glassM2: 900,
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
  project: Project | null; // корпус; для дверей в нишу — null
  doors?: DoorsResult; // двери купе, если есть
  scene: Scene; // для 3D и картинки
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
  const doorsOnly = order.kind === 'doors';
  const project = doorsOnly ? null : buildProject(order);
  const { parts, errors, warnings } = project ? calculate(project) : { parts: [] as Part[], errors: [] as string[], warnings: [] as string[] };
  const lines: Line[] = [];
  const tier = order.hardware;
  const add = (group: Group, name: string, qty: number, unit: string, price: number) => {
    if (qty > 0) lines.push({ group, name, qty: r2(qty), unit, price, sum: Math.round(qty * price) });
  };

  // Двери купе: в нишу — по чистовому проёму, у шкафа-купе — по проёму корпуса.
  let doors: DoorsResult | undefined;
  if (doorsOnly) doors = calcDoors(order.size.width, order.size.height, order.doors);
  else if (project && order.kind === 'coupe') {
    const m = project.modules[0];
    doors = calcDoors(m.width - 2 * project.thickness, m.height - 2 * project.thickness, order.doors, m.sliding?.railAllowance ?? 0);
  }
  if (doors) {
    errors.push(...doors.errors);
    parts.push(...boardParts(doors));
  }

  const doorParts = parts.filter((p) => role(p) === 'door');
  const ldspFronts = order.facade === 'ldsp';
  const bodyParts = parts.filter((p) => role(p) !== 'back' && role(p) !== 'fill' && (role(p) !== 'door' || ldspFronts));
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

  if (order.facade !== 'ldsp' && doorParts.length) {
    const facadeArea = doorParts.reduce((a, p) => a + area(p), 0);
    const names = { mdf_film: 'Фасады МДФ в плёнке', mdf_paint: 'Фасады МДФ крашеные', acrylic: 'Фасады акрил' } as const;
    add('Фасады', names[order.facade], facadeArea, 'м²', prices.facadeM2[order.facade]);
  }

  // Фурнитура — по количеству дверей, полок и корпусов.
  const modules = project?.modules ?? [];
  const hinges = doorParts.reduce((a, p) => a + hingesFor(p.length), 0);
  const shelves = parts.filter((p) => role(p) === 'shelf').length;
  const kitchenModules = modules.filter((m) => m.kitchen);
  const legs = kitchenModules.filter((m) => m.kitchen!.kind !== 'wall').length * 4;
  const hangers = kitchenModules.filter((m) => m.kitchen!.kind === 'wall').length * 2;
  add('Фурнитура', 'Петли', hinges, 'шт.', prices.hinge[tier]);
  add('Фурнитура', 'Ручки', doorParts.length, 'шт.', prices.handle[tier]);
  add('Фурнитура', 'Полкодержатели', shelves * 4, 'шт.', prices.shelfSupport[tier]);
  add('Фурнитура', 'Ножки регулируемые', legs, 'шт.', prices.leg[tier]);
  add('Фурнитура', 'Навесы для верхних шкафов', hangers, 'шт.', prices.hanger[tier]);
  add('Фурнитура', 'Крепёж, конфирматы, мелочи', modules.length, 'корпус', prices.fastenersPerModule[tier]);

  if (doors) {
    add('Двери купе', 'Система на дверь: профили, ролики, крепёж, щётка', doors.count, 'дверь', prices.coupeDoor[tier]);
    add('Двери купе', 'Направляющие верхняя + нижняя', doors.railMeters, 'пог. м', prices.railsPerM);
    add('Двери купе', 'Разделительный профиль', doors.dividerMeters, 'м', prices.dividerPerM);
    add('Двери купе', 'Зеркало 4 мм', doors.area.mirror, 'м²', prices.mirrorM2);
    add('Двери купе', 'Стекло 4 мм', doors.area.glass, 'м²', prices.glassM2);
    add('Двери купе', 'Вставки ДСП 10 мм', doors.area.board, 'м²', prices.boardFillM2);
  }

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
  if (!doorsOnly) {
    summary.push(`Корпус из ЛДСП 18 мм${ldspFronts || !doorParts.length ? '' : ', фасады — ' + { mdf_film: 'МДФ в плёнке', mdf_paint: 'МДФ крашеный', acrylic: 'акрил' }[order.facade as Exclude<Facade, 'ldsp'>]}`);
  }
  if (doorParts.length) summary.push(`${doorParts.length} ${plural(doorParts.length, 'дверь', 'двери', 'дверей')} на ${hinges} ${plural(hinges, 'петле', 'петлях', 'петлях')}`);
  if (doors) {
    summary.push(`${doors.count} ${plural(doors.count, 'дверь', 'двери', 'дверей')} купе ${Math.round(doors.doorWidth)}×${Math.round(doors.doorHeight)} мм`);
    const fills = [...new Set(doors.pieces.map((f) => fillInfo[f.fill].title.toLowerCase()))];
    summary.push(`Наполнение: ${fills.join(', ')}`);
    summary.push(`Профиль ADS, цвет ${colorNames[order.doors.color].title.toLowerCase()}`);
  }
  if (shelves) summary.push(`${shelves} ${plural(shelves, 'полка', 'полки', 'полок')}`);
  if (order.kind === 'kitchen' && order.kitchen.worktop) summary.push('Столешница');
  if (doors) summary.push({ eco: 'Раздвижная система эконом', standard: 'Раздвижная система стандарт', premium: 'Раздвижная система премиум' }[tier]);
  if (doorParts.length || (modules.length && !doors)) summary.push({ eco: 'Фурнитура эконом-класса', standard: 'Фурнитура с доводчиками', premium: 'Фурнитура Blum' }[tier]);
  if (order.delivery) summary.push('Доставка');
  if (order.install) summary.push(doorsOnly ? 'Установка дверей' : 'Сборка и установка у вас дома');

  const worktop = order.kind === 'kitchen' && order.kitchen.worktop;
  const scene = project
    ? buildScene(project, { worktop, sliding: doors, profileColor: colorNames[order.doors.color].swatch })
    : nicheScene(order.size, doors!, colorNames[order.doors.color].swatch);

  return {
    ok: errors.length === 0,
    problems: errors,
    warnings,
    project,
    doors,
    scene,
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
