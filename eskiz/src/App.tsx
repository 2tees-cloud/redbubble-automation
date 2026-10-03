import { useEffect, useMemo, useState } from 'react';
import { checkOrder, newOrder, orderTitle, statusInfo, type Order } from './engine/order';
import { calcQuote } from './engine/pricing';
import {
  loadCompany, loadOrders, loadPrices, money, saveCompany, saveOrders, savePrices,
} from './storage';
import OrderEditor from './ui/OrderEditor';
import ClientView from './ui/ClientView';
import Proposal from './ui/Proposal';
import Settings from './ui/Settings';
import Workshop from './ui/Workshop';

// Адреса экранов: #/, #/o/<id>, #/o/<id>/client, #/o/<id>/shop, #/settings,
// #/v/<код> — страница для клиента по ссылке.
// Кнопка «Назад» на телефоне работает как ожидается.
type Route = { page: 'list' } | { page: 'settings' } | { page: 'view'; code: string } | { page: 'order' | 'client' | 'shop'; id: string };

function parse(hash: string): Route {
  const [, a, id, b] = hash.replace(/^#/, '').split('/');
  if (a === 'settings') return { page: 'settings' };
  if (a === 'v' && id) return { page: 'view', code: id };
  if (a === 'o' && id) return { page: b === 'client' ? 'client' : b === 'shop' ? 'shop' : 'order', id };
  return { page: 'list' };
}

const go = (hash: string) => {
  window.location.hash = hash;
};

export default function App() {
  const [route, setRoute] = useState<Route>(() => parse(window.location.hash));
  const [orders, setOrders] = useState<Order[]>(loadOrders);
  const [prices, setPrices] = useState(loadPrices);
  const [company, setCompany] = useState(loadCompany);

  useEffect(() => {
    const onHash = () => {
      setRoute(parse(window.location.hash));
      window.scrollTo(0, 0);
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);
  useEffect(() => saveOrders(orders), [orders]);
  useEffect(() => savePrices(prices), [prices]);
  useEffect(() => saveCompany(company), [company]);

  const current = 'id' in route ? orders.find((o) => o.id === route.id) : undefined;
  const quote = useMemo(() => (current && !checkOrder(current).length ? calcQuote(current, prices) : null), [current, prices]);

  const update = (o: Order) => setOrders((all) => all.map((x) => (x.id === o.id ? { ...o, updatedAt: new Date().toISOString() } : x)));
  const create = () => {
    const o = newOrder();
    setOrders((all) => [o, ...all]);
    go(`/o/${o.id}`);
  };
  const remove = (id: string) => {
    if (!confirm('Удалить этот расчёт?')) return;
    setOrders((all) => all.filter((o) => o.id !== id));
    go('/');
  };
  const duplicate = (o: Order) => {
    const copy = { ...newOrder(), ...o, id: newOrder().id, status: 'quote' as const, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() };
    setOrders((all) => [copy, ...all]);
    go(`/o/${copy.id}`);
  };

  let title = 'Мои расчёты';
  let back: string | null = null;
  let body: React.ReactNode;

  if (route.page === 'view') {
    // Клиент видит только своё предложение: без списка, настроек и кнопки «Назад».
    return (
      <div className="app">
        <main><ClientView code={route.code} /></main>
      </div>
    );
  }

  if (route.page === 'settings') {
    title = 'Настройки и цены';
    back = '/';
    body = <Settings prices={prices} company={company} onPrices={setPrices} onCompany={setCompany} />;
  } else if (route.page !== 'list') {
    if (!current) {
      back = '/';
      body = <div className="empty">Расчёт не найден. <button className="link" onClick={() => go('/')}>К списку</button></div>;
    } else if (route.page === 'order') {
      title = orderTitle(current);
      back = '/';
      body = (
        <>
          <OrderEditor
            order={current}
            prices={prices}
            onChange={update}
            onProposal={() => go(`/o/${current.id}/client`)}
            onWorkshop={() => go(`/o/${current.id}/shop`)}
          />
          <div className="danger-zone">
            <button className="link" onClick={() => duplicate(current)}>Сделать копию</button>
            <button className="link danger" onClick={() => remove(current.id)}>Удалить расчёт</button>
          </div>
        </>
      );
    } else if (!quote || !quote.ok) {
      back = `/o/${current.id}`;
      body = <div className="empty">Сначала исправьте размеры в расчёте.</div>;
    } else if (route.page === 'client') {
      title = 'Предложение клиенту';
      back = `/o/${current.id}`;
      body = <Proposal order={current} quote={quote} company={company} />;
    } else {
      title = 'Для цеха';
      back = `/o/${current.id}`;
      body = <Workshop order={current} quote={quote} />;
    }
  } else {
    body = <OrderList orders={orders} prices={prices} onCreate={create} />;
  }

  return (
    <div className="app">
      <header className="top no-print">
        {back !== null ? (
          <button className="icon" aria-label="Назад" onClick={() => go(back!)}>←</button>
        ) : (
          <span className="logo" aria-hidden>Э</span>
        )}
        <h1>{title}</h1>
        {route.page === 'list' && (
          <button className="icon" aria-label="Настройки и цены" onClick={() => go('/settings')}>⚙</button>
        )}
      </header>
      <main>{body}</main>
    </div>
  );
}

function OrderList({ orders, prices, onCreate }: { orders: Order[]; prices: ReturnType<typeof loadPrices>; onCreate: () => void }) {
  return (
    <div className="list">
      <button className="primary big" onClick={onCreate}>+ Новый расчёт</button>
      {orders.length === 0 ? (
        <div className="welcome">
          <h2>Посчитайте мебель за минуту</h2>
          <ol>
            <li>Выберите, что делаем: шкаф, купе, кухню…</li>
            <li>Впишите размеры и выберите материал.</li>
            <li>Отправьте клиенту цену и картинку.</li>
          </ol>
          <p className="small muted">Свои цены на плиту и фурнитуру укажите в настройках ⚙ — один раз.</p>
        </div>
      ) : (
        <ul className="orders">
          {orders.map((o) => {
            const ok = !checkOrder(o).length;
            const q = ok ? calcQuote(o, prices) : null;
            return (
              <li key={o.id}>
                <a href={`#/o/${o.id}`}>
                  <div>
                    <b>{orderTitle(o)}</b>
                    <small>{[o.client.name, new Date(o.updatedAt).toLocaleDateString('ru-RU')].filter(Boolean).join(' · ')}</small>
                  </div>
                  <div className="right">
                    <b>{q?.ok ? money(q.total) : '—'}</b>
                    <span className={`status ${o.status}`}>{statusInfo[o.status]}</span>
                  </div>
                </a>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
