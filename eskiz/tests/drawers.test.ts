import { describe, expect, it } from 'vitest';
import { defaultSlides, drawerLayout, drawersFor, slideLength, type DrawerModule } from '../src/engine/drawers';
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

  it('шариковые (боковой монтаж): короб снаружи = проём − 26, ЛДСП 18', () => {
    const d = drawerLayout(mod({}), defaultProject, { name: 'Шариковые', mount: 'side', widthDeduct: 26, lengthDeduct: 0 });
    expect(d.errors).toEqual([]);
    // фасады: (720 − 4 × 2) / 3 = 237,33; ширина 600 − 4
    expect(d.fronts[0].h).toBeCloseTo(237.33, 2);
    expect(d.fronts[0].w).toBe(596);
    // проём 600 − 36 = 564; короб снаружи 538, внутри 538 − 36 = 502
    expect(d.box.w).toBe(538);
    expect(d.box.inner).toBe(502);
    const front = d.parts.find((p) => p.id === 'm1:dfb:1-1')!;
    expect(front).toMatchObject({ length: 502, thickness: 18 });
    expect(front.width).toBeCloseTo(187.3, 1);
    expect(d.parts.filter((p) => p.id.includes(':dside:'))).toHaveLength(6);
    expect(d.parts.find((p) => p.id === 'm1:dside:1-1')).toMatchObject({ length: 500, thickness: 18 });
    expect(d.parts.find((p) => p.id === 'm1:dbottom:1')).toMatchObject({ length: 500, width: 538, thickness: 3 });
  });

  it('скрытый монтаж Blum: короб внутри = проём − 42, длина = направляющая − 10', () => {
    const d = drawerLayout(mod({}), defaultProject, defaultSlides.premium);
    expect(d.box.inner).toBe(522); // 564 − 42
    expect(d.box.w).toBe(558); // 522 + 2 × 18
    expect(d.box.length).toBe(490); // 500 − 10
    expect(d.parts.find((p) => p.id === 'm1:dfb:1-2')!.length).toBe(522);
    expect(d.warnings.join()).toMatch(/запил 2 мм/);
    expect(defaultSlides.standard.name).toMatch(/Hettich/);
    expect(defaultSlides.eco.name).toMatch(/GIFF PRIME/);
  });

  it('свои вычеты из настроек', () => {
    const d = drawerLayout(mod({}), defaultProject, { name: 'Hettich Quadro', mount: 'concealed', widthDeduct: 40, lengthDeduct: 5 });
    expect(d.box.inner).toBe(524);
    expect(d.box.length).toBe(495);
  });

  it('понятные ошибки', () => {
    expect(drawerLayout(mod({ drawers: 6, height: 400 }), defaultProject, defaultSlides.eco).errors.join()).toMatch(/слишком много ящиков/);
    expect(drawerLayout(mod({ depth: 250 }), defaultProject, defaultSlides.eco).errors.join()).toMatch(/глубина/);
    expect(drawerLayout(mod({}), defaultProject, { ...defaultSlides.premium, widthDeduct: 0 }).errors.join()).toMatch(/шире проёма/);
  });
});

describe('ящики в заказе', () => {
  it('комод 1000 × 900: 4 ящика, направляющие, короба из ЛДСП 18', () => {
    const q = calcQuote(order({ kind: 'dresser', size: { width: 1000, height: 900, depth: 450 } }));
    expect(q.problems).toEqual([]);
    expect(q.lines.find((l) => l.name.startsWith('Направляющие ящиков'))?.qty).toBe(4);
    expect(q.lines.find((l) => l.name === 'Ручки')?.qty).toBe(4);
    expect(q.lines.some((l) => l.name.includes('16 мм'))).toBe(false);
    expect(q.parts.filter((p) => p.id.includes(':dside:')).every((p) => p.thickness === 18)).toBe(true);
    expect(q.lines.find((l) => l.name.startsWith('Направляющие ящиков'))?.name).toMatch(/Hettich/);
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

  it('МДФ: фасады ящиков к фасадчикам, короба — в общий файл ЛДСП 18', () => {
    const o = order({ kind: 'dresser', facade: 'mdf_paint', size: { width: 1000, height: 900, depth: 450 } });
    const q = calcQuote(o);
    expect(facadeParts(o, q.parts).every((p) => p.id.includes(':dfront:'))).toBe(true);
    expect(facadeParts(o, q.parts)).toHaveLength(4);
    expect(viyarGroups(cuttingParts(o, q.parts)).map((g) => g.thickness).sort((a, b) => a - b)).toEqual([3, 18]);
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
