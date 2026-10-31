// Простой заказ клиента и превращение его в проект с корпусами.
// Пользователь не задаёт секции, полки и планки — всё подбирается само.
import { defaultProject, type Module, type Project } from './furniture';
import { makeModule } from './kitchen';
import { defaultDoors, designFor, suggestCount, type DoorsSpec, type ProfileId } from './doors';
import { drawersFor, type DrawerModule } from './drawers';
import { CORNER, ROW_OFFSET, type KitchenModule, type WallRow } from './corner';

export type Kind = 'wardrobe' | 'coupe' | 'doors' | 'kitchen' | 'cabinet' | 'dresser' | 'shelving';
export type Facade = 'ldsp' | 'mdf_film' | 'mdf_paint' | 'acrylic';
export type Tier = 'eco' | 'standard' | 'premium';
export type Color = 'white' | 'oak' | 'walnut' | 'graphite';
export type Status = 'quote' | 'agreed' | 'production' | 'done';

export interface Order {
  id: string;
  createdAt: string;
  updatedAt: string;
  status: Status;
  client: { name: string; phone: string; address: string };
  kind: Kind;
  size: { width: number; height: number; depth: number };
  kitchen: {
    /** Прямая или угловая («Г»). Для угловой: стена A — с мойкой и пеналами, стена B — вторая. */
    shape: 'straight' | 'corner';
    bottomLength: number;
    topLength: number;
    /** Стена B, от угла: длина низа и верха. */
    sideLength: number;
    sideTop: number;
    sink: boolean;
    tallCount: number;
    worktop: boolean;
    drawerUnits: number;
  };
  /** Двери купе: для шкафа-купе и для дверей в нишу. */
  doors: DoorsSpec;
  facade: Facade;
  hardware: Tier;
  color: Color;
  delivery: boolean;
  install: boolean;
  note: string;
}

export const kindInfo: Record<Kind, { title: string; hint: string }> = {
  wardrobe: { title: 'Шкаф', hint: 'Распашные двери' },
  coupe: { title: 'Шкаф-купе', hint: 'Корпус с дверями купе' },
  doors: { title: 'Двери купе', hint: 'В готовую нишу' },
  kitchen: { title: 'Кухня', hint: 'Нижние и верхние шкафы' },
  cabinet: { title: 'Тумба', hint: 'Невысокая, с дверцами' },
  dresser: { title: 'Комод', hint: 'С выдвижными ящиками' },
  shelving: { title: 'Стеллаж', hint: 'Открытые полки' },
};

export const facadeInfo: Record<Facade, { title: string; hint: string }> = {
  ldsp: { title: 'ДСП', hint: 'Самый доступный' },
  mdf_film: { title: 'МДФ в плёнке', hint: 'Фрезеровка, под дерево' },
  mdf_paint: { title: 'МДФ крашеный', hint: 'Матовый или глянец' },
  acrylic: { title: 'Акрил', hint: 'Глубокий глянец' },
};

export const tierInfo: Record<Tier, { title: string; hint: string }> = {
  eco: { title: 'Эконом', hint: 'Простые петли, направляющие GIFF PRIME' },
  standard: { title: 'Стандарт', hint: 'Доводчики, Hettich' },
  premium: { title: 'Премиум', hint: 'Blum — тихо и надолго' },
};

export const colorInfo: Record<Color, { title: string; swatch: string }> = {
  white: { title: 'Белый', swatch: '#e9e6df' },
  oak: { title: 'Светлый дуб', swatch: '#d9bd91' },
  walnut: { title: 'Орех', swatch: '#927053' },
  graphite: { title: 'Графит', swatch: '#50595a' },
};

export const statusInfo: Record<Status, string> = {
  quote: 'Расчёт',
  agreed: 'Клиент согласен',
  production: 'В работе',
  done: 'Готово',
};

// Размеры по умолчанию для каждого вида мебели и допустимые границы.
export const sizeDefaults: Record<Exclude<Kind, 'kitchen'>, Order['size']> = {
  wardrobe: { width: 1800, height: 2400, depth: 600 },
  coupe: { width: 2000, height: 2400, depth: 600 },
  doors: { width: 2000, height: 2500, depth: 600 },
  cabinet: { width: 1200, height: 800, depth: 450 },
  dresser: { width: 1000, height: 900, depth: 450 },
  shelving: { width: 1000, height: 2000, depth: 350 },
};

export const sizeLimits: Record<Exclude<Kind, 'kitchen'>, Record<'width' | 'height' | 'depth', [number, number]>> = {
  wardrobe: { width: [400, 6000], height: [600, 3000], depth: [300, 800] },
  coupe: { width: [1200, 3000], height: [1500, 3000], depth: [450, 800] },
  // Для дверей в нишу это чистовой проём; глубина ниши нужна только для картинки.
  doors: { width: [1000, 6000], height: [400, 3240], depth: [100, 1500] },
  cabinet: { width: [300, 3000], height: [300, 1200], depth: [250, 700] },
  dresser: { width: [400, 3000], height: [300, 1400], depth: [300, 650] },
  shelving: { width: [300, 6000], height: [300, 3000], depth: [200, 700] },
};

export const kitchenLimits = { bottomLength: [600, 7000], topLength: [0, 7000], tallCount: [0, 3], drawerUnits: [0, 6] } as const;

const newId = () =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : Date.now().toString(36) + Math.random().toString(36).slice(2);

export function newOrder(): Order {
  const now = new Date().toISOString();
  return {
    id: newId(),
    createdAt: now,
    updatedAt: now,
    status: 'quote',
    client: { name: '', phone: '', address: '' },
    kind: 'wardrobe',
    size: { ...sizeDefaults.wardrobe },
    kitchen: { shape: 'straight', bottomLength: 2400, topLength: 1800, sideLength: 1800, sideTop: 1200, sink: true, tallCount: 0, worktop: true, drawerUnits: 1 },
    doors: structuredClone(defaultDoors),
    facade: 'ldsp',
    hardware: 'standard',
    color: 'white',
    delivery: true,
    install: true,
    note: '',
  };
}

export function orderTitle(o: Order) {
  const m = (v: number) => (v / 1000).toFixed(1).replace('.', ',');
  if (o.kind === 'kitchen' && o.kitchen.shape === 'corner') return `Угловая кухня ${m(o.kitchen.bottomLength)} × ${m(o.kitchen.sideLength)} м`;
  if (o.kind === 'kitchen') return `Кухня ${m(o.kitchen.bottomLength)} м`;
  if (o.kind === 'doors') return `Двери купе в проём ${o.size.width}×${o.size.height}`;
  return `${kindInfo[o.kind].title} ${o.size.width}×${o.size.height}×${o.size.depth}`;
}

/** Проверка, понятная клиенту: возвращает список простых замечаний. */
export function checkOrder(o: Order): string[] {
  const issues: string[] = [];
  const name = { width: 'Ширина', height: 'Высота', depth: 'Глубина' } as const;
  if (o.kind === 'kitchen') {
    const k = o.kitchen;
    const [bMin, bMax] = kitchenLimits.bottomLength;
    if (!(k.bottomLength >= bMin && k.bottomLength <= bMax)) issues.push(`Длина низа — от ${bMin} до ${bMax} мм.`);
    if (!(k.topLength >= 0 && k.topLength <= kitchenFreeTop(o))) issues.push(`Длина верха — не больше ${kitchenFreeTop(o)} мм (над нижними шкафами без пеналов).`);
    if (!(k.tallCount >= 0 && k.tallCount <= 3)) issues.push('Пеналов — от 0 до 3.');
    if (!(k.drawerUnits >= 0 && k.drawerUnits <= 6)) issues.push('Тумб с ящиками — от 0 до 6.');
    const free = kitchenFreeTop(o);
    if (k.sink && free < 800) issues.push('Под мойку нужно хотя бы 800 мм низа (не считая пеналов).');
    if (!k.sink && free > 0 && free < 300) issues.push('Нижний шкаф не может быть уже 300 мм — измените длину или число пеналов.');
    if (k.shape === 'corner') {
      if (!(k.sideLength >= 900 && k.sideLength <= 5000)) issues.push('Вторая стена, низ — от 900 до 5000 мм (600 из них занимает угол).');
      if (free < CORNER.baseWidth + (k.sink ? 800 : 0)) issues.push(`На первой стене нужно ${CORNER.baseWidth + (k.sink ? 800 : 0)} мм под угловой шкаф${k.sink ? ' и мойку' : ''} (не считая пеналов).`);
      if (!(k.sideTop >= 0 && k.sideTop <= k.sideLength)) issues.push('Вторая стена, верх — не длиннее низа.');
      if (k.topLength > 0 && k.sideTop > 0 && k.topLength < CORNER.wallWidth) issues.push(`Верх первой стены — от ${CORNER.wallWidth} мм: там стоит угловой навесной шкаф.`);
    }
    return issues;
  }
  const lim = sizeLimits[o.kind];
  for (const key of ['width', 'height', 'depth'] as const) {
    const [min, max] = lim[key];
    const v = o.size[key];
    if (!(v >= min && v <= max)) issues.push(`${name[key]} — от ${min} до ${max} мм.`);
  }
  return issues;
}

/** Сколько места остаётся для верхних шкафов (над пеналами их не ставим). */
export function kitchenFreeTop(o: Order) {
  return Math.max(0, o.kitchen.bottomLength - 600 * o.kitchen.tallCount);
}

/** Делит длину на равные части не шире maxPart. */
function split(length: number, maxPart: number): number[] {
  if (length <= 0) return [];
  const n = Math.ceil(length / maxPart);
  const base = Math.floor(length / n);
  return Array.from({ length: n }, (_, i) => (i === n - 1 ? length - base * (n - 1) : base));
}

const clampInt = (v: number, min: number, max: number) => Math.max(min, Math.min(max, Math.round(v)));

/** Делит ряд кухни на шкафы до 600 мм; остаток меньше 200 мм закрывается планкой, а не шкафом. */
const kitchenSplit = (length: number) => (length < CORNER.minModule ? [] : split(length, 600));

function kitchenModules(o: Order): Module[] {
  const k = o.kitchen;
  const corner = k.shape === 'corner';
  const modules: KitchenModule[] = [];
  let drawerUnits = Math.round(k.drawerUnits);
  let n = 0;
  const add = (kind: 'base' | 'wall' | 'tall' | 'sink', width: number, positionX: number, extra: Partial<KitchenModule> = {}) => {
    n += 1;
    const m: KitchenModule = makeModule(kind, `k${n}`);
    m.width = width;
    m.positionX = positionX;
    m.elevation = kind === 'wall' ? 1450 : 100;
    if (m.kitchen) m.kitchen.fronts = width > 600 ? 2 : 1;
    m.name = `${m.name} ${width}`;
    Object.assign(m, extra);
    modules.push(m);
    return m;
  };
  // Первые нижние тумбы — с тремя ящиками вместо двери и полки.
  const maybeDrawers = (m: KitchenModule) => {
    if (drawerUnits <= 0) return;
    Object.assign(m, { drawers: 3, doors: false, shelves: 0, name: `Тумба с ящиками ${m.width}` });
    drawerUnits -= 1;
  };

  // Стена A: [угловой] [тумбы] [мойка] [пеналы]; верх: [угловой навесной] [навесные].
  const lowerFree = kitchenFreeTop(o);
  let x = 0;
  if (corner) {
    // Глухой угловой: дверь только на открытой части, фасадов в старом расчёте нет — их считает corner.ts.
    add('base', CORNER.baseWidth, 0, { blind: CORNER.baseBlind, doors: false, name: `Угловая тумба ${CORNER.baseWidth}` });
    x = CORNER.baseWidth;
  }
  // Остаток меньше 300 мм не делаем отдельным шкафом — отдаём его мойке.
  const rest = lowerFree - x - (k.sink ? 800 : 0);
  const sinkWidth = k.sink ? (rest > 0 && rest < 300 ? 800 + rest : 800) : 0;
  for (const w of split(lowerFree - x - sinkWidth, 600)) {
    maybeDrawers(add('base', w, x));
    x += w;
  }
  if (k.sink) {
    add('sink', sinkWidth, x);
    x += sinkWidth;
  }
  for (let i = 0; i < k.tallCount; i++) {
    add('tall', 600, x);
    x += 600;
  }
  const cornerTop = corner && k.topLength > 0 && k.sideTop > 0;
  let top = 0;
  if (cornerTop) {
    add('wall', CORNER.wallWidth, 0, { blind: CORNER.wallBlind, doors: false, name: `Угловой навесной ${CORNER.wallWidth}` });
    top = CORNER.wallWidth;
  }
  for (const w of kitchenSplit(Math.min(k.topLength, lowerFree) - top)) {
    add('wall', w, top);
    top += w;
  }

  if (corner) {
    // Стена B: идёт от угла к зрителю. Внизу угол занимает 600 мм (глубина тумбы A + зазор).
    const low: WallRow = { depth: 560, startZ: -CORNER.gap, length: k.sideLength - CORNER.baseZone };
    let bx = 0;
    for (const w of kitchenSplit(low.length)) {
      maybeDrawers(add('base', w, ROW_OFFSET + bx, { row: low }));
      bx += w;
    }
    low.length = bx;
    if (k.sideTop > 0) {
      // Верх стены B начинается перед фасадами навесных стены A (или от самой стены, если их нет).
      const startZ = k.topLength > 0 ? 560 - 320 - CORNER.wallGap : 560;
      const up: WallRow = { depth: 320, startZ, length: k.sideTop - (560 - startZ) };
      let ux = 0;
      for (const w of kitchenSplit(up.length)) {
        add('wall', w, ROW_OFFSET + ux, { row: up });
        ux += w;
      }
      up.length = ux;
    }
  }
  return modules;
}

function bodyModules(o: Order): Module[] {
  const { width, height, depth } = o.size;
  // Широкий шкаф собираем из нескольких корпусов: так их легче везти и заносить.
  // Комод — не шире 1000 мм на корпус: длинные ящики прогибаются и тяжело ходят.
  const maxBody = o.kind === 'coupe' ? 3000 : o.kind === 'dresser' ? 1000 : 2400;
  const widths = split(width, maxBody);
  let x = 0;
  return widths.map((w, i) => {
    const id = `m${i + 1}`;
    const name = widths.length > 1 ? `Корпус ${i + 1}` : kindInfo[o.kind].title;
    const positionX = x;
    x += w;
    if (o.kind === 'coupe') {
      // Двери считает engine/doors.ts по проёму корпуса. Здесь — только отступ полок под систему
      // и совместимость со старым расчётом корпуса (он знает 2–3 двери и базовые профили).
      const profile = o.doors.profile.replace('L', '') as Exclude<ProfileId, `${string}L`>;
      const count = Math.min(3, Math.max(2, o.doors.count || suggestCount(w - 36, o.doors.profile))) as 2 | 3;
      const fills = Array.from({ length: count }, (_, j) => designFor(o.doors, j)[0].fill);
      return {
        id, name, width: w, height, depth, positionX,
        sections: clampInt(w / 900, 1, 6),
        shelves: clampInt(height / 500, 1, 8),
        doors: true, back: true,
        sliding: { profile, count, reserve: 90, railAllowance: 0, fills },
      };
    }
    if (o.kind === 'shelving') {
      return { id, name, width: w, height, depth, positionX, sections: clampInt(Math.ceil(w / 800), 1, 6), shelves: clampInt(height / 350, 1, 10), doors: false, back: true };
    }
    if (o.kind === 'dresser') {
      const m: DrawerModule = { id, name, width: w, height, depth, positionX, sections: 1, shelves: 0, doors: false, back: true, drawers: drawersFor(height) };
      return m;
    }
    if (o.kind === 'cabinet') {
      return { id, name, width: w, height, depth, positionX, sections: clampInt(Math.ceil(w / 600), 1, 6), shelves: height >= 600 ? 1 : 0, doors: true, back: true };
    }
    return { id, name, width: w, height, depth, positionX, sections: clampInt(Math.ceil(w / 600), 1, 6), shelves: clampInt(height / 500, 1, 8), doors: true, back: true };
  });
}

export function buildProject(o: Order): Project {
  return {
    ...defaultProject,
    name: orderTitle(o),
    material: `ЛДСП 18 мм, ${colorInfo[o.color].title}`,
    finish: o.color,
    modules: o.kind === 'kitchen' ? kitchenModules(o) : bodyModules(o),
  };
}
