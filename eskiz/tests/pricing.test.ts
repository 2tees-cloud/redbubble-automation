import { describe, expect, it } from 'vitest';
import { newOrder, buildProject, checkOrder, type Order } from '../src/engine/order';
import { calcQuote, hingesFor, defaultPrices, cuttingParts, facadeParts } from '../src/engine/pricing';
import { viyarGroups } from '../src/engine/viyar-export';
import { buildScene } from '../src/engine/geometry';

const order = (patch: Partial<Order>): Order => ({ ...newOrder(), ...patch });

describe('простой заказ → корпуса', () => {
  it('шкаф 1800 — один корпус на 3 двери', () => {
    const q = calcQuote(order({ kind: 'wardrobe' }));
    expect(q.problems).toEqual([]);
    expect(q.project!.modules).toHaveLength(1);
    expect(q.parts.filter((p) => p.id.includes(':door:'))).toHaveLength(3);
  });
  it('широкий шкаф делится на корпуса', () => {
    const q = calcQuote(order({ kind: 'wardrobe', size: { width: 4800, height: 2400, depth: 600 } }));
    expect(q.problems).toEqual([]);
    expect(q.project!.modules).toHaveLength(2);
  });
  it('купе: 2 двери до 2400, 3 двери шире', () => {
    expect(buildProject(order({ kind: 'coupe', size: { width: 2000, height: 2400, depth: 600 } })).modules[0].sliding?.count).toBe(2);
    const q = calcQuote(order({ kind: 'coupe', size: { width: 2800, height: 2400, depth: 600 } }));
    expect(q.problems).toEqual([]);
    expect(q.project!.modules[0].sliding?.count).toBe(3);
    expect(q.doors?.count).toBe(3);
    expect(q.lines.find((l) => l.name.startsWith('Система'))?.qty).toBe(3);
  });
  it('кухня без наложений, мойка и пенал', () => {
    const q = calcQuote(order({ kind: 'kitchen', kitchen: { bottomLength: 3000, topLength: 2400, sink: true, tallCount: 1, worktop: true } }));
    expect(q.problems).toEqual([]);
    const kinds = q.project!.modules.map((m) => m.kitchen?.kind);
    expect(kinds.filter((k) => k === 'sink')).toHaveLength(1);
    expect(kinds.filter((k) => k === 'tall')).toHaveLength(1);
    expect(q.lines.find((l) => l.name === 'Столешница')?.qty).toBe(2.4);
  });
  it('узкий остаток отдаётся мойке', () => {
    const q = calcQuote(order({ kind: 'kitchen', kitchen: { bottomLength: 1000, topLength: 0, sink: true, tallCount: 0, worktop: false } }));
    expect(q.problems).toEqual([]);
    expect(q.project!.modules.map((m) => m.width)).toEqual([1000]);
  });
  it('все виды мебели считаются без ошибок', () => {
    for (const kind of ['wardrobe', 'coupe', 'cabinet', 'shelving'] as const) {
      for (const width of [600, 1200, 1800, 2400, 3000]) {
        const o = order({ kind, size: { width: kind === 'coupe' ? Math.max(1200, width) : width, height: kind === 'cabinet' ? 800 : 2400, depth: 500 } });
        if (checkOrder(o).length) continue;
        expect(calcQuote(o).problems, `${kind} ${width}`).toEqual([]);
      }
    }
    for (const bottomLength of [800, 1200, 1900, 2400, 3600, 5000]) for (const tallCount of [0, 1, 2]) for (const sink of [true, false]) {
      const o = order({ kind: 'kitchen', kitchen: { bottomLength, topLength: 1200, sink, tallCount, worktop: true } });
      o.kitchen.topLength = Math.min(1200, Math.max(0, bottomLength - 600 * tallCount));
      if (checkOrder(o).length) continue;
      expect(calcQuote(o).problems, `kitchen ${bottomLength} ${tallCount} ${sink}`).toEqual([]);
    }
  });
});

describe('3D-сцена', () => {
  it('двери шкафа на 3 двери не открываются навстречу друг другу', () => {
    const sc = buildScene(buildProject(order({ kind: 'wardrobe' })));
    const hinges = sc.boxes.filter((b) => b.hinge).map((b) => b.hinge);
    expect(hinges).toEqual(['left', 'right', 'right']);
    expect(sc.boxes.filter((b) => b.role === 'handle')).toHaveLength(3);
  });
  it('кухня: столешница только над нижними шкафами, цоколь под ними', () => {
    const o = order({ kind: 'kitchen' });
    const sc = buildScene(buildProject(o), { worktop: true });
    expect(sc.boxes.some((b) => b.role === 'worktop')).toBe(true);
    expect(sc.boxes.filter((b) => b.role === 'plinth').every((b) => b.y === 0)).toBe(true);
  });
  it('у купе в описании нет фасадов', () => {
    const q = calcQuote(order({ kind: 'coupe', facade: 'acrylic' }));
    expect(q.summary[0]).toBe('Корпус из ЛДСП 18 мм');
  });
});

describe('цена', () => {
  it('петли по высоте двери', () => {
    expect([700, 1200, 1800, 2400].map(hingesFor)).toEqual([2, 3, 4, 5]);
  });
  it('премиум дороже эконома, МДФ дороже ДСП', () => {
    const base = order({ kind: 'wardrobe' });
    expect(calcQuote({ ...base, hardware: 'premium' }).total).toBeGreaterThan(calcQuote({ ...base, hardware: 'eco' }).total);
    expect(calcQuote({ ...base, facade: 'mdf_paint' }).total).toBeGreaterThan(calcQuote({ ...base, facade: 'ldsp' }).total);
  });
  it('итог складывается из строк и округлён до 100', () => {
    const q = calcQuote(order({ kind: 'wardrobe' }));
    const mat = q.lines.filter((l) => l.group !== 'Работа').reduce((a, l) => a + l.sum, 0);
    expect(q.materials).toBe(mat);
    expect(q.total % 100).toBe(0);
    expect(q.total).toBeGreaterThanOrEqual(q.product + q.install + q.delivery);
    expect(q.profit).toBe(q.total - q.cost);
  });
  it('без монтажа и доставки дешевле', () => {
    const base = order({ kind: 'wardrobe' });
    expect(calcQuote({ ...base, install: false, delivery: false }).total).toBeLessThan(calcQuote(base).total);
    expect(calcQuote({ ...base, install: false, delivery: false }, defaultPrices).install).toBe(0);
  });
  it('МДФ-фасады не попадают в раскрой ДСП', () => {
    const q = calcQuote(order({ kind: 'wardrobe', facade: 'mdf_paint' }));
    expect(q.lines.some((l) => l.group === 'Фасады')).toBe(true);
    const o = order({ kind: 'wardrobe', facade: 'mdf_paint' });
    expect(cuttingParts(o, q.parts).some((p) => p.id.includes(':door:'))).toBe(false);
    expect(facadeParts(o, q.parts)).toHaveLength(3);
    // В каждом файле для ВіЯр — один материал: ЛДСП корпуса и ХДФ отдельно.
    expect(viyarGroups(cuttingParts(o, q.parts)).map((g) => g.thickness).sort()).toEqual([18, 3]);
  });
});

describe('ссылка для клиента', () => {
  it('кодируется и читается обратно без прайса и заметок', async () => {
    const { encodeShare, decodeShare } = await import('../src/share');
    const { defaultCompany } = await import('../src/storage');
    const o = order({ kind: 'kitchen', note: 'клиент торгуется', client: { name: 'Олена', phone: '+380', address: '' } });
    const q = calcQuote(o);
    const code = await encodeShare(o, q, defaultCompany);
    expect(code.length).toBeLessThan(1500);
    const back = await decodeShare(code);
    expect(back?.total).toBe(q.total);
    expect(back?.order.client.name).toBe('Олена');
    expect(JSON.stringify(back)).not.toContain('торгуется');
    expect(JSON.stringify(back)).not.toContain('ldspSheet');
    expect(await decodeShare('zBROKEN')).toBeNull();
  });
});

describe('двери купе в заказе', () => {
  it('двери в нишу: без корпуса, цена из системы, зеркал и направляющих', () => {
    const o = order({ kind: 'doors', size: { width: 2400, height: 2600, depth: 600 } });
    const q = calcQuote(o);
    expect(q.problems).toEqual([]);
    expect(q.project).toBeNull();
    expect(q.doors?.count).toBe(3);
    expect(q.lines.some((l) => l.group === 'Плита и кромка')).toBe(false);
    expect(q.lines.find((l) => l.name.startsWith('Направляющие'))?.qty).toBe(2.4);
    expect(q.summary.some((s) => s.includes('Корпус'))).toBe(false);
    expect(q.scene.boxes.some((b) => b.role === 'wall')).toBe(true);
  });
  it('вставки ДСП идут в ВіЯр отдельным файлом и не в листы корпуса', () => {
    const o = order({ kind: 'coupe', doors: { ...newOrder().doors, designs: [{ sections: [{ fill: 'board' }, { fill: 'mirror' }] }] } });
    const q = calcQuote(o);
    expect(q.problems).toEqual([]);
    const groups = viyarGroups(cuttingParts(o, q.parts)).map((g) => g.thickness).sort((a, b) => a - b);
    expect(groups).toEqual([3, 10, 18]);
    const plain = calcQuote(order({ kind: 'coupe' }));
    expect(q.lines.find((l) => l.name.startsWith('ЛДСП'))?.qty).toBe(plain.lines.find((l) => l.name.startsWith('ЛДСП'))?.qty);
  });
  it('шкаф-купе: двери по проёму корпуса (ширина − 2 × 18)', () => {
    const q = calcQuote(order({ kind: 'coupe', size: { width: 2000, height: 2400, depth: 600 } }));
    expect(q.doors?.openingWidth).toBe(1964);
    expect(q.doors?.doorHeight).toBe(2364 - 43);
  });
  it('неверное число дверей — понятная ошибка', () => {
    const o = order({ kind: 'doors', size: { width: 3000, height: 2600, depth: 600 } });
    o.doors = { ...o.doors, count: 2 };
    expect(calcQuote(o).problems.join()).toMatch(/Подойдёт дверей/);
  });
});
