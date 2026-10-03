// Ссылка для клиента: заказ, итог и «что входит» упакованы прямо в адрес.
// Прайс мастера, себестоимость и заметки в ссылку не попадают.
import { newOrder, type Order } from './engine/order';
import type { Quote } from './engine/pricing';
import type { Company } from './storage';

export interface Shared {
  v: 1;
  order: Omit<Order, 'note'>;
  company: Pick<Company, 'name' | 'phone' | 'leadTime' | 'validDays'>;
  total: number;
  summary: string[];
}

const toB64 = (bytes: Uint8Array) => {
  let s = '';
  bytes.forEach((b) => (s += String.fromCharCode(b)));
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
};
const fromB64 = (s: string) => {
  const bin = atob(s.replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
};

async function pipe(bytes: Uint8Array, stream: CompressionStream | DecompressionStream) {
  const out = new Response(new Blob([bytes as BlobPart]).stream().pipeThrough(stream));
  return new Uint8Array(await out.arrayBuffer());
}

export async function encodeShare(order: Order, quote: Quote, company: Company): Promise<string> {
  const { note: _note, ...rest } = order;
  const data: Shared = {
    v: 1,
    order: rest,
    company: { name: company.name, phone: company.phone, leadTime: company.leadTime, validDays: company.validDays },
    total: quote.total,
    summary: quote.summary,
  };
  const json = new TextEncoder().encode(JSON.stringify(data));
  // Сжатие делает ссылку в 2–3 раза короче; старые браузеры получают несжатую.
  if (typeof CompressionStream !== 'undefined') return 'z' + toB64(await pipe(json, new CompressionStream('deflate-raw')));
  return 'j' + toB64(json);
}

export async function decodeShare(code: string): Promise<Shared | null> {
  try {
    const kind = code[0];
    let bytes = fromB64(code.slice(1));
    if (kind === 'z') bytes = await pipe(bytes, new DecompressionStream('deflate-raw'));
    else if (kind !== 'j') return null;
    const data = JSON.parse(new TextDecoder().decode(bytes)) as Shared;
    if (data.v !== 1 || typeof data.total !== 'number') return null;
    return { ...data, order: { ...newOrder(), ...data.order }, summary: Array.isArray(data.summary) ? data.summary.map(String) : [] };
  } catch {
    return null;
  }
}

export const shareUrl = (code: string) => `${location.origin}${location.pathname}#/v/${code}`;
