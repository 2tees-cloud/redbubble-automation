// Конструктор дверей купе: сколько дверей, на сколько частей делится дверь и из чего каждая вставка.
import { useEffect, useState } from 'react';
import {
  colorNames, dividers, fillInfo, profiles, suggestCount, validCounts,
  type DoorDesign, type DoorsResult, type DoorsSpec, type Fill, type ProfileColor, type Section,
} from '../engine/doors';
import { Choice, Toggle } from './fields';

const baseFillColors: Record<Fill, string> = { mirror: '#c9dde3', glass: '#e4ece9', board: '#c8b597' };
const fmt = (n: number) => String(n).replace('.', ',');

export default function DoorDesigner({
  spec, openingWidth, result, boardColor, onChange,
}: {
  spec: DoorsSpec;
  boardColor: string;
  openingWidth: number;
  result?: DoorsResult;
  onChange: (s: DoorsSpec) => void;
}) {
  const counts = validCounts(openingWidth, spec.profile);
  const auto = suggestCount(openingWidth, spec.profile);
  const count = result?.count ?? (spec.count || auto);
  const set = (patch: Partial<DoorsSpec>) => onChange({ ...spec, ...patch });
  const fillColors = { ...baseFillColors, board: boardColor };

  // Сколько рисунков редактируем: один на все двери или по одному на каждую.
  const designs: DoorDesign[] = spec.same
    ? [spec.designs[0] ?? { sections: [{ fill: 'mirror' }] }]
    : Array.from({ length: count }, (_, i) => spec.designs[i] ?? spec.designs[0] ?? { sections: [{ fill: 'mirror' }] });
  const setDesign = (i: number, d: DoorDesign) => {
    const next = [...designs];
    next[i] = d;
    set({ designs: next });
  };

  const countOptions = Object.fromEntries([
    ['0', { title: `Авто · ${auto}`, hint: 'подберём сами' }],
    ...counts.map((n) => [String(n), { title: `${n}`, hint: result && n === count ? `по ${fmt(result.doorWidth)} мм` : '' }]),
  ]) as Record<string, { title: string; hint?: string }>;

  return (
    <div className="doors-designer">
      <Choice label="Сколько дверей" value={String(spec.count && counts.includes(spec.count) ? spec.count : 0)} options={countOptions} onChange={(v) => set({ count: Number(v) })} />
      {result && (
        <p className="door-size">
          Каждая дверь: <b>{fmt(result.doorWidth)} × {fmt(result.doorHeight)} мм</b> · перехлёстов {result.overlaps}
        </p>
      )}
      <Choice
        label="Цвет профиля"
        value={spec.color}
        options={colorNames}
        swatches={Object.fromEntries(Object.entries(colorNames).map(([k, v]) => [k, v.swatch])) as Record<ProfileColor, string>}
        onChange={(color) => set({ color })}
      />
      <Toggle
        label="Все двери одинаковые"
        checked={spec.same}
        onChange={(same) => set({ same, designs: same ? [designs[0]] : Array.from({ length: count }, (_, i) => spec.designs[i] ?? designs[0]) })}
      />
      <div className="door-cards">
        {designs.map((d, i) => (
          <DoorCard
            key={i}
            title={spec.same ? 'Все двери' : `Дверь ${i + 1}`}
            design={d}
            pieces={result?.doors[spec.same ? 0 : i]?.pieces}
            fillColors={fillColors}
            onChange={(nd) => setDesign(i, nd)}
          />
        ))}
      </div>
      <details className="more">
        <summary>Профиль и разделитель ADS</summary>
        <div className="row2">
          <div className="field">
            <label htmlFor="profile">Вертикальный профиль</label>
            <select id="profile" value={spec.profile} onChange={(e) => set({ profile: e.target.value as DoorsSpec['profile'] })}>
              {Object.keys(profiles).map((p) => <option key={p} value={p}>{p.endsWith('L') ? `LITE ${p}` : `BRAND ${p}`}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="divider">Разделительный профиль</label>
            <select id="divider" value={spec.divider} onChange={(e) => set({ divider: e.target.value as DoorsSpec['divider'] })}>
              {Object.keys(dividers).map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
        </div>
        <p className="small muted">Вычеты — по таблицам 1–3 каталога ADS BRAND.</p>
      </details>
    </div>
  );
}

function DoorCard({ title, design, pieces, fillColors, onChange }: { title: string; design: DoorDesign; pieces?: { height: number; width: number }[]; fillColors: Record<Fill, string>; onChange: (d: DoorDesign) => void }) {
  const sections = design.sections.length ? design.sections : [{ fill: 'mirror' as Fill }];
  const setSections = (s: Section[]) => onChange({ sections: s });
  const split = (n: number) =>
    setSections(Array.from({ length: n }, (_, k) => ({ fill: sections[k]?.fill ?? sections[sections.length - 1].fill })));
  const total = pieces?.reduce((a, p) => a + p.height, 0) ?? sections.length;

  return (
    <div className="door-card">
      <div className="door-preview" aria-hidden>
        {sections.map((s, k) => (
          <div key={k} style={{ flexGrow: pieces?.[k]?.height ?? total / sections.length, background: fillColors[s.fill] }} />
        ))}
      </div>
      <div className="door-edit">
        <b>{title}</b>
        <div className="split">
          {['Целая', '2 части', '3 части', '4 части', '5 частей'].map((label, k) => (
            <button key={label} className={sections.length === k + 1 ? 'on' : ''} onClick={() => split(k + 1)}>
              {label}
            </button>
          ))}
        </div>
        {sections.map((s, k) => (
          <div className="section-row" key={k}>
            <span className="section-name">{sections.length === 1 ? 'Вставка' : k === 0 ? 'Верх' : k === sections.length - 1 ? 'Низ' : `${k + 1}-я`}</span>
            <div className="fills">
              {(Object.keys(fillInfo) as Fill[]).map((f) => (
                <button key={f} className={s.fill === f ? 'on' : ''} onClick={() => setSections(sections.map((x, j) => (j === k ? { ...x, fill: f } : x)))}>
                  <i style={{ background: fillColors[f] }} />
                  {fillInfo[f].title}
                </button>
              ))}
            </div>
            {sections.length > 1 && (
              <HeightInput value={s.height} onChange={(height) => setSections(sections.map((x, j) => (j === k ? { ...x, height } : x)))} />
            )}
            {pieces?.[k] && <span className="piece">{fmt(pieces[k].height)} × {fmt(pieces[k].width)}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

/** Высота вставки: пусто — «авто», делится поровну. */
function HeightInput({ value, onChange }: { value?: number; onChange: (v?: number) => void }) {
  const [text, setText] = useState(value ? String(value) : '');
  useEffect(() => {
    if ((value ?? '') !== (text === '' ? '' : Number(text.replace(',', '.')))) setText(value ? String(value) : '');
  }, [value]);
  return (
    <label className="height-input">
      <input
        inputMode="decimal"
        placeholder="авто"
        aria-label="Высота вставки, мм"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          const v = Number(e.target.value.replace(',', '.'));
          onChange(e.target.value.trim() === '' || !(v > 0) ? undefined : v);
        }}
      />
      <span>мм</span>
    </label>
  );
}
