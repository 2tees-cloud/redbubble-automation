import { useState } from 'react';
import { csv, type Part } from '../engine/furniture';
import type { Order } from '../engine/order';
import { cuttingParts, facadeParts, type Group, type Quote } from '../engine/pricing';
import { slidingCsv } from '../engine/sliding';
import { viyarCsv, viyarGroups, viyarImportHelp, viyarIssues, type Orientation } from '../engine/viyar-export';
import { money } from '../storage';

function download(name: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: 'text/csv;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function Workshop({ order, quote }: { order: Order; quote: Quote }) {
  const [orientation, setOrientation] = useState<Orientation>('horizontal');
  const [error, setError] = useState('');
  const cut = cuttingParts(order, quote.parts);
  const fronts = facadeParts(order, quote.parts);
  const groups = viyarGroups(cut);
  const issues = viyarIssues(cut);
  // Латиница в имени: некоторые браузеры отбрасывают кириллические имена файлов.
  const base = `eskiz-${order.id.slice(0, 6).toUpperCase()}`;
  const byGroup = new Map<Group, typeof quote.lines>();
  for (const l of quote.lines) byGroup.set(l.group, [...(byGroup.get(l.group) ?? []), l]);

  const exportViyar = (parts: Part[], index: number) => {
    setError('');
    try {
      download(`${base}-viyar-${index}.csv`, viyarCsv(parts, orientation));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="workshop">
      <section className="card-block">
        <h2>Деньги</h2>
        <div className="money-row">
          <div><span>Клиенту</span><strong>{money(quote.total)}</strong></div>
          <div><span>Себестоимость</span><strong>{money(quote.cost)}</strong></div>
          <div><span>Остаётся вам</span><strong>{money(quote.profit)}</strong><small>вместе с монтажом</small></div>
        </div>
        <table className="lines">
          <thead><tr><th>Позиция</th><th>Кол-во</th><th>Цена</th><th>Сумма</th></tr></thead>
          {[...byGroup].map(([group, lines]) => (
            <tbody key={group}>
              <tr className="group"><td colSpan={4}>{group}</td></tr>
              {lines.map((l, i) => (
                <tr key={i}>
                  <td>{l.name}</td>
                  <td>{l.qty} {l.unit}</td>
                  <td>{money(l.price)}</td>
                  <td>{money(l.sum)}</td>
                </tr>
              ))}
            </tbody>
          ))}
          <tfoot>
            <tr><td colSpan={3}>Материалы и работа цеха</td><td>{money(quote.materials + quote.labor)}</td></tr>
            <tr><td colSpan={3}>С наценкой</td><td>{money(quote.product)}</td></tr>
            {quote.install > 0 && <tr><td colSpan={3}>Монтаж</td><td>{money(quote.install)}</td></tr>}
            {quote.delivery > 0 && <tr><td colSpan={3}>Доставка</td><td>{money(quote.delivery)}</td></tr>}
            <tr className="sum"><td colSpan={3}>Итого клиенту (округлено)</td><td>{money(quote.total)}</td></tr>
          </tfoot>
        </table>
        <p className="small muted">Цены берутся из «Настроек». Листы считаются по площади с запасом на отходы; точный раскрой сделает ВіЯр или KRONAS.</p>
      </section>

      <section className="card-block">
        <h2>Файлы для порезки</h2>
        <p className="small">Один файл — один материал. Загрузите его в кабинет ВіЯр: «Імпорт деталей». <a href={viyarImportHelp} target="_blank" rel="noreferrer">Инструкция ВіЯр</a></p>
        <div className="field inline">
          <label htmlFor="orient">Длина детали на схеме ВіЯр</label>
          <select id="orient" value={orientation} onChange={(e) => setOrientation(e.target.value as Orientation)}>
            <option value="horizontal">Горизонтально</option>
            <option value="vertical">Вертикально</option>
          </select>
        </div>
        <div className="downloads">
          {groups.map((g) => (
            <button key={g.id} disabled={issues.length > 0} onClick={() => exportViyar(g.parts, g.index)}>
              ВіЯр: {g.thickness === 18 ? 'ЛДСП 18 мм' : g.thickness === 3 ? 'ХДФ 3 мм' : `${g.material}`} · {g.parts.length} дет.
            </button>
          ))}
          <button onClick={() => download(`${base}-detali.csv`, csv(quote.parts))}>Все детали (Excel)</button>
          {quote.project.modules.filter((m) => m.sliding).map((m) => (
            <button key={m.id} onClick={() => download(`${base}-kupe-${m.id}.csv`, slidingCsv(m, quote.project.thickness))}>Купе: профили и заполнение</button>
          ))}
        </div>
        {(error || issues.length > 0) && <p className="issues">{error || issues.join(' ')}</p>}
      </section>

      {fronts.length > 0 && (
        <section className="card-block">
          <h2>Фасады — заказать отдельно</h2>
          <table className="lines">
            <thead><tr><th>Корпус</th><th>Высота × ширина, мм</th></tr></thead>
            <tbody>{fronts.map((p) => <tr key={p.id}><td>{p.module}</td><td>{p.length} × {p.width}</td></tr>)}</tbody>
          </table>
        </section>
      )}

      <section className="card-block">
        <h2>Детали · {quote.parts.length}</h2>
        <div className="scroll-x">
          <table className="lines parts">
            <thead><tr><th>Корпус</th><th>Деталь</th><th>Длина</th><th>Ширина</th><th>Кромка</th></tr></thead>
            <tbody>
              {quote.parts.map((p) => (
                <tr key={p.id}>
                  <td>{p.module}</td>
                  <td>{p.name}</td>
                  <td>{p.length}</td>
                  <td>{p.width}</td>
                  <td>{p.edges.filter((e) => e > 0).length ? p.edges.map((e) => (e > 0 ? e : '–')).join(' / ') : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {quote.warnings.length > 0 && (
        <section className="card-block">
          <h2>Проверить перед запуском</h2>
          <ul className="warn">{[...new Set(quote.warnings)].map((w) => <li key={w}>{w}</li>)}</ul>
        </section>
      )}
    </div>
  );
}
