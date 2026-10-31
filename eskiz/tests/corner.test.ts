import { describe, expect, it } from 'vitest';
import { CORNER, type KitchenModule } from '../src/engine/corner';
import { worldBox } from '../src/engine/geometry';
import { checkOrder, newOrder, type Order } from '../src/engine/order';
import { calcQuote, facadeParts } from '../src/engine/pricing';

const corner = (patch: Partial<Order['kitchen']> = {}): Order => {
  const o = newOrder();
  return { ...o, kind: 'kitchen', kitchen: { ...o.kitchen, shape: 'corner', bottomLength: 3000, topLength: 2400, sideLength: 2400, sideTop: 1800, drawerUnits: 0, ...patch } };
};

describe('угловая кухня «Г»', () => {
  it('раскладка: угловые на стене 1, шкафы стены 2 после угла', () => {
    const q = calcQuote(corner());
    expect(q.problems).toEqual([]);
    const ms = q.project!.modules as KitchenModule[];
    const a = ms.filter((m) => !m.row);
    const b = ms.filter((m) => m.row);
    // стена 1: угловая 1000 + тумбы до мойки + мойка 800
    expect(a[0]).toMatchObject({ width: CORNER.baseWidth, blind: CORNER.baseBlind });
    expect(a.find((m) => m.kitchen?.kind === 'wall')).toMatchObject({ width: CORNER.wallWidth, blind: CORNER.wallBlind });
    // стена 2: низ 2400 − 600 угла = 1800 → 3 тумбы по 600; верх 1800 − 340 = 1460 → 3 навесных
    expect(b.filter((m) => m.kitchen?.kind === 'base').map((m) => m.width)).toEqual([600, 600, 600]);
    expect(b.filter((m) => m.kitchen?.kind === 'wall').reduce((s, m) => s + m.width, 0)).toBe(1460);
  });

  it('в 3D шкафы двух стен не пересекаются', () => {
    const q = calcQuote(corner());
    const body = q.scene.boxes.filter((b) => b.role === 'body').map((b) => worldBox(b, q.scene.frames));
    const hit = (p: typeof body[0], r: typeof body[0]) =>
      p.x < r.x + r.w - 1 && r.x < p.x + p.w - 1 && p.y < r.y + r.h - 1 && r.y < p.y + p.h - 1 && p.z < r.z + r.d - 1 && r.z < p.z + p.d - 1;
    const a = q.scene.boxes.map((b, i) => [b, i] as const).filter(([b]) => b.role === 'body' && !b.frame).map(([, i]) => worldBox(q.scene.boxes[i]));
    const b = q.scene.boxes.filter((x) => x.role === 'body' && x.frame).map((x) => worldBox(x, q.scene.frames));
    expect(a.length).toBeGreaterThan(0);
    expect(b.length).toBeGreaterThan(0);
    for (const p of a) for (const r of b) expect(hit(p, r)).toBe(false);
    // стена 2 стоит у левой стены и идёт к зрителю
    expect(Math.min(...b.map((x) => x.x))).toBeGreaterThanOrEqual(0);
    // низ стены 2 — перед фасадами стены 1; верх — перед её навесными (их фасады на z = 240)
    expect(Math.max(...b.filter((x) => x.y < 1000).map((x) => x.z + x.d))).toBeLessThanOrEqual(-CORNER.gap);
    expect(Math.max(...b.filter((x) => x.y > 1400).map((x) => x.z + x.d))).toBeLessThanOrEqual(240 - CORNER.wallGap);
    expect(body.length).toBe(a.length + b.length);
  });

  it('угловой шкаф: одна дверь на петлях и фальш-панель', () => {
    const o = corner();
    const q = calcQuote(o);
    const m = (q.project!.modules as KitchenModule[])[0];
    const fronts = q.parts.filter((p) => p.id.startsWith(`${m.id}:`) && /:(door|blind):/.test(p.id));
    expect(fronts.map((p) => p.name)).toEqual(['Фасад углового шкафа', 'Фальш-панель (глухая часть угла)']);
    // дверь: 1000 − 600 − 2 × 2 = 396; панель: 600 − 2
    expect(fronts[0].width).toBe(396);
    expect(fronts[1].width).toBe(598);
    // МДФ: и дверь, и фальш-панель — к фасадчикам
    const mdf = { ...o, facade: 'mdf_paint' as const };
    expect(facadeParts(mdf, calcQuote(mdf).parts).some((p) => p.id.includes(':blind:'))).toBe(true);
  });

  it('столешница — по обеим стенам', () => {
    const q = calcQuote(corner({ tallCount: 0 }));
    // стена 1: 3000; стена 2: 1800
    expect(q.lines.find((l) => l.name === 'Столешница')?.qty).toBe(4.8);
  });

  it('проверки размеров', () => {
    expect(checkOrder(corner({ sideLength: 500 })).join()).toMatch(/Вторая стена/);
    expect(checkOrder(corner({ bottomLength: 1500 })).join()).toMatch(/угловой шкаф/);
    expect(checkOrder(corner({ topLength: 500 })).join()).toMatch(/угловой навесной/);
    for (const sideLength of [900, 1300, 2000, 3500]) for (const tallCount of [0, 1]) {
      const o = corner({ sideLength, sideTop: Math.min(sideLength, 1200), tallCount });
      if (checkOrder(o).length) continue;
      expect(calcQuote(o).problems, `${sideLength} ${tallCount}`).toEqual([]);
    }
  });
});
