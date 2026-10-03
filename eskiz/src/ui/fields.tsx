import { useEffect, useId, useState, type ReactNode } from 'react';

/** Крупные карточки выбора — одно касание, без выпадающих списков. */
export function Choice<T extends string>({
  label, value, options, onChange, swatches,
}: {
  label: string;
  value: T;
  options: Record<T, { title: string; hint?: string }>;
  onChange: (v: T) => void;
  swatches?: Partial<Record<T, string>>;
}) {
  return (
    <fieldset className="choice">
      <legend>{label}</legend>
      <div className="choice-grid">
        {(Object.keys(options) as T[]).map((key) => (
          <label key={key} className={key === value ? 'card on' : 'card'}>
            <input type="radio" checked={key === value} onChange={() => onChange(key)} />
            {swatches?.[key] && <span className="swatch" style={{ background: swatches[key] }} />}
            <b>{options[key].title}</b>
            {options[key].hint && <small>{options[key].hint}</small>}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/** Поле для числа: можно спокойно стирать и печатать, число уходит наружу, когда оно валидно. */
export function NumberField({
  label, value, onChange, unit = 'мм', min, max, hint,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  unit?: string;
  min?: number;
  max?: number;
  hint?: ReactNode;
}) {
  const id = useId();
  const [text, setText] = useState(String(value));
  useEffect(() => {
    if (Number(text.replace(',', '.')) !== value) setText(String(value));
  }, [value]);
  const n = Number(text.replace(',', '.'));
  const bad = text.trim() === '' || !Number.isFinite(n) || (min !== undefined && n < min) || (max !== undefined && n > max);
  return (
    <div className={bad ? 'field bad' : 'field'}>
      <label htmlFor={id}>{label}</label>
      <div className="input-unit">
        <input
          id={id}
          inputMode="decimal"
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            const v = Number(e.target.value.replace(',', '.'));
            if (e.target.value.trim() !== '' && Number.isFinite(v)) onChange(v);
          }}
        />
        {unit && <span>{unit}</span>}
      </div>
      {hint && <small>{hint}</small>}
    </div>
  );
}

export function TextField({ label, value, onChange, type = 'text', placeholder }: { label: string; value: string; onChange: (v: string) => void; type?: string; placeholder?: string }) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input id={id} type={type} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

export function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>{label}</span>
    </label>
  );
}
