// То, что клиент видит по ссылке: 3D, описание, цена и кнопка «Позвонить».
import { lazy, Suspense, useEffect, useState } from 'react';
import type { Project } from '../engine/furniture';
import { buildProject, checkOrder, colorInfo, facadeInfo, kindInfo, orderTitle, tierInfo, type Order } from '../engine/order';
import { decodeShare, type Shared } from '../share';
import { money } from '../storage';
import FurnitureView from './FurnitureView';

const Viewer3D = lazy(() => import('./Viewer3D'));

export default function ClientView({ code }: { code: string }) {
  const [state, setState] = useState<{ data: Shared; order: Order; project: Project } | null | 'loading'>('loading');
  useEffect(() => {
    let alive = true;
    decodeShare(code).then((data) => {
      if (!alive) return;
      const order: Order | null = data ? { ...data.order, note: '' } : null;
      setState(data && order && !checkOrder(order).length ? { data, order, project: buildProject(order) } : null);
    });
    return () => {
      alive = false;
    };
  }, [code]);

  if (state === 'loading') return <div className="empty">Загружаем проект…</div>;
  if (!state) return <div className="empty">Ссылка повреждена. Попросите мастера прислать её ещё раз.</div>;

  const { data, order, project } = state;
  const hasFacades = order.kind !== 'coupe' && order.kind !== 'shelving';
  const worktop = order.kind === 'kitchen' && order.kitchen.worktop;
  const phone = data.company.phone.replace(/[^\d+]/g, '');

  return (
    <div className="client-view">
      <p className="from">{data.company.name}</p>
      <h2>{orderTitle(order)}</h2>
      <Suspense fallback={<FurnitureView project={project} color={order.color} doors worktop={worktop} />}>
        <Viewer3D project={project} color={order.color} facade={order.facade} worktop={worktop} />
      </Suspense>

      <div className="spec card-block">
        <dl>
          <dt>Изделие</dt><dd>{kindInfo[order.kind].title}</dd>
          <dt>Цвет корпуса</dt><dd>{colorInfo[order.color].title}</dd>
          {hasFacades && <><dt>Фасады</dt><dd>{facadeInfo[order.facade].title}</dd></>}
          <dt>Фурнитура</dt><dd>{tierInfo[order.hardware].title}: {tierInfo[order.hardware].hint}</dd>
          <dt>Срок</dt><dd>{data.company.leadTime}</dd>
        </dl>
        <div>
          <h3>Что входит</h3>
          <ul>{data.summary.map((s) => <li key={s}>{s}</li>)}</ul>
        </div>
      </div>

      <div className="total">
        <span>Стоимость</span>
        <strong>{money(data.total)}</strong>
      </div>
      <p className="small muted">Предложение действует {data.company.validDays} дней. Точная цена фиксируется после замера.</p>

      {phone && (
        <div className="contact">
          <a className="button primary" href={`tel:${phone}`}>Позвонить мастеру</a>
          <a className="button" href={`viber://chat?number=${encodeURIComponent(phone)}`}>Viber</a>
        </div>
      )}
    </div>
  );
}
