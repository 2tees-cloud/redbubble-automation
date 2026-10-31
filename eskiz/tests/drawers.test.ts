import { describe, expect, it } from 'vitest';
import { drawerLayout, drawersFor, slideLength, type DrawerModule } from '../src/engine/drawers';
import { defaultProject } from '../src/engine/furniture';
import { buildProject, newOrder, type Order } from '../src/engine/order';
import { calcQuote, cuttingParts, facadeParts } from '../src/engine/pricing';
import { viyarGroups } from '../src/engine/viyar-export';

const order = (patch: Partial<Order>): Order => ({ ...newOrder(), ...patch });
const mod = (patch: Partial<DrawerModule>): DrawerModule => ({ id: 'm1', name: 'Комод', width: 600, height: 720, depth: 560, sections: 1, shelves: 0, doors: false, back: true, drawers: 3, ...patch });

describe('ящики', () => {
  it('направляющая — самая длинная, что влезает в глубину', () => {
    expect(slideLength(560)).toBe(500);
    expect(slideLength(450)).toBe(400);
    expect(slideLength(250)).toBe(0);
    expect([400, 700, 900, 1300].map(drawersFor)).toEqual([2, 3, 4, 6]);
  });

  it('тумба 600 × 720, 3 ящика, шариковые направляющие', () => {
    const d = drawerLayout(mod({}), defaultProject, 'standard');
    expect(d.errors).toEqual([]);
    // фасады: (720 − 4 × 2) / 3 = 237,33; ширина 600 − 4
    expect(d.fronts[0].h).toBeCloseTo(237.33, 2);
    expect(d.fronts[0].w).toBe(596);
    // короб: внутренняя ширина 564 − 26 = 538; лоб/зад 538 − 32 = 506; высота 237,3 − 50
    expect(d.box.w).toBe(538);
    const front = d.parts.find((p) => p.id === 'm1:dfb:1-1')!;
    expect(front.length).toBe(506);
    expect(front.width).toBeCloseTo(187.3, 1);
    expect(d.parts.filter((p) => p.id.includes(':dside:'))).toHaveLength(6);
    expect(d.parts.find((p) => p.id === 'm1:dside:1-1')!.length).toBe(500);
    expect(d.parts.find((p) => p.id === 'm1:dbottom:1')).toMatchObject({ length: 500, width: 538, thickness: 3 });
  });

  it('Blum скрытого монтажа — короб шире (зазор 10 мм)', () => {
    expect(drawerLayout(mod({}), defaultProject, 'premium').box.w).toBe(554);
  });

  it('понятные ошибки', () => {
    expect(drawerLayout(mod({ drawers: 6, height: 400 }), defaultProject, 'eco').errors.join()).toMatch(/слишком много ящиков/);
    expect(drawerLayout(mod({ depth: 250 }), defaultProject, 'eco').errors.join()).toMatch(/глубина/);
  });
});

describe('ящики в заказе', () => {
  it('комод 1000 × 900: 4 ящика, направляющие, короба из ЛДСП 16', () => {
    const q = calcQuote(order({ kind: 'dresser', size: { width: 1000, height: 900, depth: 450 } }));
    expect(q.problems).toEqual([]);
    expect(q.lines.find((l) => l.name.startsWith('Направляющие ящиков'))?.qty).toBe(4);
    expect(q.lines.find((l) => l.name === 'Ручки')?.qty).toBe(4);
    expect(q.lines.find((l) => l.name.startsWith('ЛДСП 16'))?.qty).toBeGreaterThan(0);
    expect(q.lines.find((l) => l.name === 'Петли')).toBeUndefined();
    expect(q.summary.join()).toMatch(/4 ящика/);
  });

  it('широкий комод делится на корпуса до 1000 мм', () => {
    expect(buildProject(order({ kind: 'dresser', size: { width: 1600, height: 900, depth: 450 } })).modules).toHaveLength(2);
  });

  it('кухня: первая тумба с ящиками, без двери и полки', () => {
    const q = calcQuote(order({ kind: 'kitchen' }));
    expect(q.problems).toEqual([]);
    const m = q.project!.modules[0] as DrawerModule;
    expect(m.drawers).toBe(3);
    expect(q.parts.filter((p) => p.id.startsWith(`${m.id}:door`))).toHaveLength(0);
    expect(q.parts.filter((p) => p.id.startsWith(`${m.id}:dfront`))).toHaveLength(3);
  });

  it('МДФ: фасады ящиков к фасадчикам, короба — в ВіЯр отдельными файлами', () => {
    const o = order({ kind: 'dresser', facade: 'mdf_paint', size: { width: 1000, height: 900, depth: 450 } });
    const q = calcQuote(o);
    expect(facadeParts(o, q.parts).every((p) => p.id.includes(':dfront:'))).toBe(true);
    expect(facadeParts(o, q.parts)).toHaveLength(4);
    expect(viyarGroups(cuttingParts(o, q.parts)).map((g) => g.thickness).sort((a, b) => a - b)).toEqual([3, 16, 18]);
    expect(q.lines.find((l) => l.group === 'Фасады')).toBeDefined();
  });

  it('3D: короба привязаны к своим фасадам и выдвигаются', () => {
    const q = calcQuote(order({ kind: 'dresser', size: { width: 1000, height: 900, depth: 450 } }));
    const fronts = q.scene.boxes.map((b, i) => [b, i] as const).filter(([b]) => b.pull !== undefined && b.door === undefined);
    expect(fronts).toHaveLength(4);
    for (const [, i] of fronts) {
      const kids = q.scene.boxes.filter((b) => b.door === i);
      expect(kids).toHaveLength(5); // дно, задняя стенка, два бока, ручка
    }
  });
});
