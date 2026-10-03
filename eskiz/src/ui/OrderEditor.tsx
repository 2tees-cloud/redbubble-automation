import { lazy, Suspense, useMemo } from 'react';
import {
  checkOrder, colorInfo, facadeInfo, kindInfo, kitchenFreeTop, sizeDefaults, sizeLimits, statusInfo, tierInfo,
  type Kind, type Order, type Status,
} from '../engine/order';
import { calcQuote, type PriceList } from '../engine/pricing';
import { money } from '../storage';
import FurnitureView from './FurnitureView';

const Viewer3D = lazy(() => import('./Viewer3D'));
import { Choice, NumberField, TextField, Toggle } from './fields';

const coupeFills = {
  mix: { title: 'Зеркало + ДСП', hint: 'Двери чередуются' },
  mirror: { title: 'Все зеркала' },
  board: { title: 'Все из ДСП' },
} as const;

export default function OrderEditor({
  order, prices, onChange, onProposal, onWorkshop,
}: {
  order: Order;
  prices: PriceList;
  onChange: (o: Order) => void;
  onProposal: () => void;
  onWorkshop: () => void;
}) {
  const issues = checkOrder(order);
  const quote = useMemo(() => (issues.length ? null : calcQuote(order, prices)), [order, prices, issues.length]);
  const set = (patch: Partial<Order>) => onChange({ ...order, ...patch });

  const setKind = (kind: Kind) => set({ kind, ...(kind !== 'kitchen' && kind !== order.kind ? { size: { ...sizeDefaults[kind] } } : {}) });
  const size = (key: 'width' | 'height' | 'depth', v: number) => set({ size: { ...order.size, [key]: v } });
  const kitchen = (patch: Partial<Order['kitchen']>) => set({ kitchen: { ...order.kitchen, ...patch } });

  const lim = order.kind !== 'kitchen' ? sizeLimits[order.kind] : null;
  const canPrice = quote && quote.ok;
  const worktop = order.kind === 'kitchen' && order.kitchen.worktop;

  return (
    <div className="editor">
      <div className="form">
        <section>
          <h2><i>1</i>Что делаем</h2>
          <Choice label="Вид мебели" value={order.kind} options={kindInfo} onChange={setKind} />
        </section>

        <section>
          <h2><i>2</i>Размеры</h2>
          {lim ? (
            <div className="row3">
              <NumberField label="Ширина" value={order.size.width} min={lim.width[0]} max={lim.width[1]} onChange={(v) => size('width', v)} />
              <NumberField label="Высота" value={order.size.height} min={lim.height[0]} max={lim.height[1]} onChange={(v) => size('height', v)} />
              <NumberField label="Глубина" value={order.size.depth} min={lim.depth[0]} max={lim.depth[1]} onChange={(v) => size('depth', v)} />
            </div>
          ) : (
            <>
              <div className="row2">
                <NumberField label="Длина низа" value={order.kitchen.bottomLength} min={600} max={7000} onChange={(v) => kitchen({ bottomLength: v })} hint="Вдоль стены, вместе с мойкой и пеналами" />
                <NumberField label="Длина верха" value={order.kitchen.topLength} min={0} max={kitchenFreeTop(order)} onChange={(v) => kitchen({ topLength: v })} hint="0 — без верхних шкафов" />
              </div>
              <div className="row2">
                <NumberField label="Пеналов (высоких шкафов)" unit="шт." value={order.kitchen.tallCount} min={0} max={3} onChange={(v) => kitchen({ tallCount: Math.round(v) })} hint="Под холодильник, духовку и т. п." />
                <div className="toggles">
                  <Toggle label="Шкаф под мойку" checked={order.kitchen.sink} onChange={(v) => kitchen({ sink: v })} />
                  <Toggle label="Столешница" checked={order.kitchen.worktop} onChange={(v) => kitchen({ worktop: v })} />
                </div>
              </div>
            </>
          )}
          {order.kind === 'coupe' && <Choice label="Двери купе" value={order.coupeFill} options={coupeFills} onChange={(v) => set({ coupeFill: v })} />}
          {issues.length > 0 && (
            <ul className="issues">{issues.map((x) => <li key={x}>{x}</li>)}</ul>
          )}
        </section>

        <section>
          <h2><i>3</i>Материал и цвет</h2>
          {order.kind !== 'coupe' && order.kind !== 'shelving' && (
            <Choice label="Фасады (двери)" value={order.facade} options={facadeInfo} onChange={(v) => set({ facade: v })} />
          )}
          <Choice label="Цвет корпуса" value={order.color} options={colorInfo} swatches={Object.fromEntries(Object.entries(colorInfo).map(([k, v]) => [k, v.swatch]))} onChange={(v) => set({ color: v })} />
        </section>

        <section>
          <h2><i>4</i>Фурнитура</h2>
          <Choice label="Класс фурнитуры" value={order.hardware} options={tierInfo} onChange={(v) => set({ hardware: v })} />
          <div className="toggles inline">
            <Toggle label="Доставка" checked={order.delivery} onChange={(v) => set({ delivery: v })} />
            <Toggle label="Сборка и установка" checked={order.install} onChange={(v) => set({ install: v })} />
          </div>
        </section>

        <section>
          <h2><i>5</i>Клиент</h2>
          <div className="row2">
            <TextField label="Имя" value={order.client.name} onChange={(name) => set({ client: { ...order.client, name } })} />
            <TextField label="Телефон" type="tel" value={order.client.phone} onChange={(phone) => set({ client: { ...order.client, phone } })} />
          </div>
          <TextField label="Адрес" value={order.client.address} onChange={(address) => set({ client: { ...order.client, address } })} />
          <div className="field">
            <label htmlFor="note">Заметки (видите только вы)</label>
            <textarea id="note" rows={3} value={order.note} placeholder="Например: ручки чёрные, ниша под стиралку" onChange={(e) => set({ note: e.target.value })} />
          </div>
          <div className="field">
            <label htmlFor="status">Состояние заказа</label>
            <select id="status" value={order.status} onChange={(e) => set({ status: e.target.value as Status })}>
              {(Object.keys(statusInfo) as Status[]).map((s) => <option key={s} value={s}>{statusInfo[s]}</option>)}
            </select>
          </div>
        </section>
      </div>

      <aside className="result">
        {quote ? (
          <>
            <Suspense fallback={<FurnitureView project={quote.project} color={order.color} doors worktop={worktop} />}>
              <Viewer3D project={quote.project} color={order.color} facade={order.facade} worktop={worktop} />
            </Suspense>
            {canPrice ? (
              <div className="price">
                <span>Цена для клиента</span>
                <strong>{money(quote.total)}</strong>
                <ul>{quote.summary.map((s) => <li key={s}>{s}</li>)}</ul>
              </div>
            ) : (
              <div className="issues">
                <b>Не получается посчитать:</b>
                <ul>{quote.problems.slice(0, 4).map((x) => <li key={x}>{x}</li>)}</ul>
              </div>
            )}
          </>
        ) : (
          <div className="empty">Исправьте размеры — и цена появится здесь.</div>
        )}
        <div className="actions">
          <button className="primary" disabled={!canPrice} onClick={onProposal}>Предложение клиенту</button>
          <button disabled={!canPrice} onClick={onWorkshop}>Для цеха</button>
        </div>
      </aside>

      {canPrice && (
        <div className="sticky-price">
          <div><span>Цена</span><strong>{money(quote.total)}</strong></div>
          <button className="primary" onClick={onProposal}>Клиенту</button>
        </div>
      )}
    </div>
  );
}
