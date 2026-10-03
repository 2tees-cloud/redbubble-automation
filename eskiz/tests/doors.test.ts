import { describe, expect, it } from 'vitest';
import { boardParts, calcDoors, defaultDoors, suggestCount, validCounts, type DoorsSpec } from '../src/engine/doors';

const spec = (patch: Partial<DoorsSpec>): DoorsSpec => ({ ...defaultDoors, ...patch });

describe('двери купе по таблицам ADS BRAND', () => {
  it('2 двери, профиль 020, проём 2000 × 2400, целое зеркало', () => {
    const r = calcDoors(2000, 2400, spec({ count: 2 }));
    expect(r.errors).toEqual([]);
    expect(r.doorHeight).toBe(2357); // H − 43
    expect(r.doorWidth).toBe(1016.5); // (33 × 1 + 2000) / 2
    expect(r.pieces[0]).toMatchObject({ height: 2294, width: 978.5 }); // S − 63, L − 38
    expect(r.horizontal).toBe(966.5); // L − 50
    expect(r.profiles.find((p) => p.name.startsWith('Вертикальный'))).toMatchObject({ length: 2357, qty: 4 });
  });

  it('ДСП целиком: S − 60 × L − 35', () => {
    const r = calcDoors(2000, 2400, spec({ count: 2, designs: [{ sections: [{ fill: 'board' }] }] }));
    expect(r.pieces[0]).toMatchObject({ height: 2297, width: 981.5, thickness: 10 });
    expect(boardParts(r)).toHaveLength(2);
  });

  it('3 двери, профиль 117: ширина (50 × 2 + B) / 3, стекло L − 87', () => {
    const r = calcDoors(2900, 2600, spec({ count: 3, profile: '117' }));
    expect(r.doorWidth).toBe(1000);
    expect(r.pieces[0].width).toBe(913);
    expect(r.horizontal).toBe(900);
  });

  it('разделитель 03: зеркало + ДСП + зеркало, вычет 2 мм на каждый стык', () => {
    const r = calcDoors(2000, 2400, spec({ count: 2, designs: [{ sections: [{ fill: 'mirror' }, { fill: 'board' }, { fill: 'mirror' }] }] }));
    const d = r.doors[0];
    expect(d.dividers).toBe(2);
    // 2357 − 31,5 − 31,5 − 2 − 2 = 2290, поровну по 763,3
    expect(d.pieces.reduce((a, f) => a + f.height, 0)).toBeCloseTo(2290, 5);
    expect(d.pieces.map((f) => f.width)).toEqual([978.5, 981.5, 978.5]);
    expect(r.profiles.find((p) => p.name.startsWith('Разделительный'))).toMatchObject({ length: 966.5, qty: 4 });
  });

  it('заданная высота вставки, остальное — авто', () => {
    const r = calcDoors(2000, 2400, spec({ count: 2, divider: '31', designs: [{ sections: [{ fill: 'board', height: 400 }, { fill: 'mirror' }] }] }));
    const [top, rest] = r.doors[0].pieces;
    expect(top.height).toBe(400);
    // 2357 − 30 − 31,5 − 9 (31: стекло + ДСП) − 400
    expect(rest.height).toBe(1886.5);
  });

  it('LITE 119L и ДСП+ДСП с разделителем 32', () => {
    const r = calcDoors(1800, 2200, spec({ count: 2, profile: '119L', divider: '32', designs: [{ sections: [{ fill: 'board' }, { fill: 'board' }] }] }));
    expect(r.doorWidth).toBe(913);
    expect(r.pieces[0].width).toBe(876); // L − 37
    expect(r.pieces[0].height + r.pieces[1].height).toBeCloseTo(2157 - 60 - 34, 5);
  });

  it('разные двери: каждая по своему рисунку', () => {
    const r = calcDoors(3000, 2400, spec({ count: 3, same: false, designs: [{ sections: [{ fill: 'mirror' }] }, { sections: [{ fill: 'board' }, { fill: 'glass' }] }] }));
    expect(r.doors.map((d) => d.pieces.length)).toEqual([1, 2, 1]); // третьей не задан рисунок — как у первой
  });

  it('подбор числа дверей и ошибки', () => {
    expect(validCounts(2000, '020')).toEqual([2, 3, 4]);
    expect(suggestCount(2000, '020')).toBe(2);
    expect(suggestCount(2400, '020')).toBe(3);
    expect(calcDoors(3000, 2400, spec({ count: 2 })).errors[0]).toMatch(/Подойдёт дверей: 3, 4, 5/);
    expect(calcDoors(2000, 3400, spec({ count: 2 })).errors[0]).toMatch(/Высота двери/);
    const tooTall = calcDoors(2000, 2400, spec({ count: 2, designs: [{ sections: [{ fill: 'board', height: 1500 }, { fill: 'board', height: 900 }, { fill: 'mirror' }] }] }));
    expect(tooTall.errors.join()).toMatch(/не хватает высоты/);
  });
});
