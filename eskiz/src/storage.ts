// Хранение на устройстве. Позже заменяется на облако без изменения интерфейса.
import { newOrder, type Order } from './engine/order';
import { defaultPrices, type PriceList } from './engine/pricing';

export interface Company {
  name: string;
  phone: string;
  leadTime: string;
  validDays: number;
}

export const defaultCompany: Company = { name: 'Моя мастерская', phone: '', leadTime: '14–21 рабочий день', validDays: 14 };

const KEYS = { orders: 'eskiz.orders.v1', prices: 'eskiz.prices.v1', company: 'eskiz.company.v1' };

function read<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function write(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Переполнено или запрещено — расчёт всё равно работает до закрытия вкладки.
  }
}

/** Дополняет сохранённые данные новыми полями, которые появились в следующих версиях. */
function merge<T>(defaults: T, saved: unknown): T {
  if (saved === null || typeof saved !== 'object' || Array.isArray(saved)) return defaults;
  const out: Record<string, unknown> = { ...(defaults as Record<string, unknown>) };
  for (const [k, v] of Object.entries(defaults as Record<string, unknown>)) {
    const s = (saved as Record<string, unknown>)[k];
    if (v !== null && typeof v === 'object' && !Array.isArray(v)) out[k] = merge(v, s);
    else if (typeof s === typeof v) out[k] = s;
  }
  return out as T;
}

export const loadOrders = (): Order[] => (read<unknown[]>(KEYS.orders) ?? []).map((o) => merge(newOrder(), o));
export const saveOrders = (orders: Order[]) => write(KEYS.orders, orders);
export const loadPrices = (): PriceList => merge(defaultPrices, read(KEYS.prices));
export const savePrices = (p: PriceList) => write(KEYS.prices, p);
export const loadCompany = (): Company => merge(defaultCompany, read(KEYS.company));
export const saveCompany = (c: Company) => write(KEYS.company, c);

export const money = (n: number) => `${Math.round(n).toLocaleString('ru-RU').replace(/,/g, ' ')} грн`;
