import { lazy, Suspense, useEffect, useState } from 'react';
import { colorInfo, facadeInfo, kindInfo, orderTitle, tierInfo, type Order } from '../engine/order';
import type { Quote } from '../engine/pricing';
import { money, type Company } from '../storage';
import { encodeShare, shareUrl } from '../share';
import FurnitureView from './FurnitureView';

const Viewer3D = lazy(() => import('./Viewer3D'));

export function proposalText(order: Order, quote: Quote, company: Company, link?: string) {
  return [
    `${company.name}${company.phone ? ', ' + company.phone : ''}`,
    `Предложение: ${orderTitle(order)}`,
    ...quote.summary.map((s) => `• ${s}`),
    `Цвет: ${colorInfo[order.color].title}`,
    `Цена: ${money(quote.total)}`,
    `Срок изготовления: ${company.leadTime}`,
    `Предложение действует ${company.validDays} дней.`,
    ...(link ? [`Посмотреть в 3D: ${link}`] : []),
  ].join('\n');
}

export default function Proposal({ order, quote, company }: { order: Order; quote: Quote; company: Company }) {
  const [copied, setCopied] = useState(false);
  const [link, setLink] = useState('');
  useEffect(() => {
    let alive = true;
    encodeShare(order, quote, company).then((code) => alive && setLink(shareUrl(code)));
    return () => {
      alive = false;
    };
  }, [order, quote, company]);
  const text = proposalText(order, quote, company, link);
  const worktop = order.kind === 'kitchen' && order.kitchen.worktop;
  const date = new Date(order.updatedAt).toLocaleDateString('ru-RU');
  const number = order.id.slice(0, 6).toUpperCase();
  const hasFacades = order.kind !== 'coupe' && order.kind !== 'shelving';

  const share = async () => {
    try {
      if (navigator.share) {
        await navigator.share({ title: orderTitle(order), text });
        return;
      }
    } catch {
      return; // пользователь закрыл окно «Поделиться»
    }
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt('Скопируйте текст', text);
    }
  };

  return (
    <div className="proposal-wrap">
      <div className="toolbar no-print">
        <button className="primary" onClick={share}>{copied ? 'Скопировано' : 'Отправить в мессенджер'}</button>
        <a className="button" href={`viber://forward?text=${encodeURIComponent(text)}`}>Viber</a>
        <a className="button" target="_blank" rel="noreferrer" href={`https://t.me/share/url?url=${encodeURIComponent(' ')}&text=${encodeURIComponent(text)}`}>Telegram</a>
        <button onClick={() => window.print()}>Печать / PDF</button>
        {link && <a className="button" href={link} target="_blank" rel="noreferrer">Как увидит клиент</a>}
      </div>
      <p className="small muted no-print">В сообщении будет ссылка: клиент откроет её на телефоне и покрутит мебель в 3D. Ваши цены и заметки в ссылку не попадают.</p>

      <article className="proposal">
        <header>
          <div>
            <h1>{company.name}</h1>
            {company.phone && <p>{company.phone}</p>}
          </div>
          <div className="meta">
            <p>Предложение № {number}</p>
            <p>{date}</p>
          </div>
        </header>

        {(order.client.name || order.client.phone) && (
          <p className="client">Для: {[order.client.name, order.client.phone, order.client.address].filter(Boolean).join(', ')}</p>
        )}

        <h2>{orderTitle(order)}</h2>
        <div className="no-print">
          <Suspense fallback={<FurnitureView project={quote.project} color={order.color} doors worktop={worktop} />}>
            <Viewer3D project={quote.project} color={order.color} facade={order.facade} worktop={worktop} />
          </Suspense>
        </div>
        <div className="print-only">
          <FurnitureView project={quote.project} color={order.color} doors worktop={worktop} />
        </div>

        <div className="spec">
          <dl>
            <dt>Изделие</dt><dd>{kindInfo[order.kind].title}</dd>
            <dt>Цвет корпуса</dt><dd>{colorInfo[order.color].title}</dd>
            {hasFacades && <><dt>Фасады</dt><dd>{facadeInfo[order.facade].title}</dd></>}
            <dt>Фурнитура</dt><dd>{tierInfo[order.hardware].title}: {tierInfo[order.hardware].hint}</dd>
            <dt>Срок</dt><dd>{company.leadTime}</dd>
          </dl>
          <div>
            <h3>Что входит</h3>
            <ul>{quote.summary.map((s) => <li key={s}>{s}</li>)}</ul>
          </div>
        </div>

        <div className="total">
          <span>Стоимость</span>
          <strong>{money(quote.total)}</strong>
        </div>
        <p className="small">Предложение действует {company.validDays} дней. Точная цена фиксируется после замера.</p>
      </article>
    </div>
  );
}
