// Угловая кухня (буква «Г»): глухой угловой шкаф и вторая стена.
//
// Стена A — вдоль задней стены, угол слева. Стена B — вдоль левой стены, идёт к зрителю.
// Угловой шкаф стоит на стене A у угла: его левая часть закрыта шкафами стены B
// («глухая» часть с фальш-панелью), справа — обычная дверь.
import type { Module, Part, Project } from './furniture';
import { makePart, type DrawerModule } from './drawers';

/** Ряд шкафов на стене B: где начинается от угла и какой глубины. */
export interface WallRow {
  /** Глубина шкафов ряда, мм. */
  depth: number;
  /** Координата z (вглубь от фасадов стены A) у угла, откуда ряд идёт к зрителю. */
  startZ: number;
  /** Длина ряда вдоль стены B, мм. */
  length: number;
}

export type KitchenModule = DrawerModule & {
  /** Модуль стоит на стене B (повёрнут на 90°). */
  row?: WallRow;
  /** Глухой угловой шкаф: ширина закрытой части у угла, мм. */
  blind?: number;
};

export const CORNER = {
  baseWidth: 1000, // нижний угловой шкаф
  wallWidth: 700, // верхний угловой шкаф
  gap: 40, // от фасадов стены A до первых шкафов стены B (столешница A — 18 + 22 мм)
  baseZone: 600, // сколько стены B занимает угол внизу: глубина 560 + 40
  baseBlind: 600, // закрытая часть нижнего углового: шкафы стены B (560) + дверь и зазор
  wallBlind: 350, // закрытая часть верхнего углового: шкафы стены B (320) + дверь и зазор
  wallGap: 20, // от фасадов верхних шкафов стены A до первых верхних шкафов стены B
  minModule: 200, // остаток уже этого не делаем шкафом — закрывается планкой
} as const;

/**
 * Модули стены B хранятся с большим сдвигом по x: старый расчёт корпусов проверяет
 * наложения только по x и высоте и не знает о второй стене. В геометрии сдвиг вычитается.
 */
export const ROW_OFFSET = 10000;

/** Фасады глухого углового шкафа: неподвижная фальш-панель у угла и дверь на правых петлях. */
export function cornerFronts(m: Module & { blind?: number }, project: Pick<Project, 'gap'>) {
  const g = project.gap;
  const blind = m.blind ?? 0;
  const h = m.height - 2 * g;
  return {
    panel: { x: g, y: g, w: blind - g, h },
    door: { x: blind + g, y: g, w: m.width - blind - 2 * g, h },
  };
}

/** Детали фасадов глухого углового шкафа: дверь (с петлями) и неподвижная фальш-панель. */
export function cornerParts(m: KitchenModule, project: Project): Part[] {
  if (!m.blind) return [];
  const f = cornerFronts(m, project);
  const e = project.edge;
  return [
    makePart(`${m.id}:door:1`, m.name, 'Фасад углового шкафа', f.door.h, f.door.w, project.thickness, project.material, [e, e, e, e]),
    makePart(`${m.id}:blind:1`, m.name, 'Фальш-панель (глухая часть угла)', f.panel.h, f.panel.w, project.thickness, project.material, [e, e, e, e]),
  ];
}
