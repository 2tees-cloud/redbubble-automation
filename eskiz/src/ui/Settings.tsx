import { defaultPrices, type PriceList, type TierPrices } from '../engine/pricing';
import type { Tier } from '../engine/order';
import { tierInfo } from '../engine/order';
import type { Company } from '../storage';
import { NumberField, TextField } from './fields';

type NumKey = { [K in keyof PriceList]: PriceList[K] extends number ? K : never }[keyof PriceList];
type TierKey = { [K in keyof PriceList]: PriceList[K] extends TierPrices ? K : never }[keyof PriceList];

const plate: [NumKey, string, string][] = [
  ['ldspSheet', 'ЛДСП 18 мм, лист 2800×2070', 'грн'],
  ['hdfSheet', 'ХДФ 3 мм, лист', 'грн'],
  ['cutPerSheet', 'Порезка, за лист', 'грн'],
  ['edgePerM', 'Кромка, материал', 'грн/м'],
  ['edgingPerM', 'Кромкование, работа', 'грн/м'],
];
const other: [NumKey, string, string][] = [
  ['mirrorM2', 'Зеркало для купе', 'грн/м²'],
  ['boardFillM2', 'Вставка ДСП в купе', 'грн/м²'],
  ['worktopPerM', 'Столешница', 'грн/м'],
  ['plinthPerM', 'Цоколь', 'грн/м'],
];
const business: [NumKey, string, string][] = [
  ['laborPercent', 'Работа цеха', '% от материалов'],
  ['markupPercent', 'Ваша наценка', '%'],
  ['installPercent', 'Монтаж', '% от цены'],
  ['delivery', 'Доставка', 'грн'],
];
const tiers: [TierKey, string][] = [
  ['hinge', 'Петля'],
  ['handle', 'Ручка'],
  ['leg', 'Ножка кухонная'],
  ['hanger', 'Навес для верхнего шкафа'],
  ['shelfSupport', 'Полкодержатель'],
  ['fastenersPerModule', 'Крепёж на один корпус'],
  ['coupeDoor', 'Система купе на одну дверь'],
];

export default function Settings({
  prices, company, onPrices, onCompany,
}: {
  prices: PriceList;
  company: Company;
  onPrices: (p: PriceList) => void;
  onCompany: (c: Company) => void;
}) {
  const num = (rows: [NumKey, string, string][]) => (
    <div className="row2">
      {rows.map(([key, label, unit]) => (
        <NumberField key={key} label={label} unit={unit} min={0} value={prices[key]} onChange={(v) => onPrices({ ...prices, [key]: v })} />
      ))}
    </div>
  );

  return (
    <div className="settings">
      <section className="card-block">
        <h2>Ваша мастерская</h2>
        <p className="small muted">Эти данные видит клиент в предложении.</p>
        <div className="row2">
          <TextField label="Название" value={company.name} onChange={(name) => onCompany({ ...company, name })} />
          <TextField label="Телефон" type="tel" value={company.phone} onChange={(phone) => onCompany({ ...company, phone })} />
          <TextField label="Срок изготовления" value={company.leadTime} onChange={(leadTime) => onCompany({ ...company, leadTime })} />
          <NumberField label="Предложение действует" unit="дней" min={1} value={company.validDays} onChange={(validDays) => onCompany({ ...company, validDays })} />
        </div>
      </section>

      <section className="card-block">
        <h2>Плита и порезка</h2>
        {num(plate)}
        <NumberField label="Полезный выход листа" unit="%" min={50} max={95} value={Math.round(prices.sheetUse * 100)} onChange={(v) => onPrices({ ...prices, sheetUse: v / 100 })} hint="80 % — значит, 20 % листа уходит в отходы" />
      </section>

      <section className="card-block">
        <h2>Фасады, за м²</h2>
        <div className="row3">
          <NumberField label="МДФ в плёнке" unit="грн" min={0} value={prices.facadeM2.mdf_film} onChange={(v) => onPrices({ ...prices, facadeM2: { ...prices.facadeM2, mdf_film: v } })} />
          <NumberField label="МДФ крашеный" unit="грн" min={0} value={prices.facadeM2.mdf_paint} onChange={(v) => onPrices({ ...prices, facadeM2: { ...prices.facadeM2, mdf_paint: v } })} />
          <NumberField label="Акрил" unit="грн" min={0} value={prices.facadeM2.acrylic} onChange={(v) => onPrices({ ...prices, facadeM2: { ...prices.facadeM2, acrylic: v } })} />
        </div>
      </section>

      <section className="card-block">
        <h2>Фурнитура, за штуку</h2>
        <div className="tier-table">
          <div className="tier-head"><span />{(Object.keys(tierInfo) as Tier[]).map((t) => <b key={t}>{tierInfo[t].title}</b>)}</div>
          {tiers.map(([key, label]) => (
            <div className="tier-row" key={key}>
              <span>{label}</span>
              {(Object.keys(tierInfo) as Tier[]).map((t) => (
                <NumberField key={t} label={`${label}, ${tierInfo[t].title}`} unit="грн" min={0} value={prices[key][t]} onChange={(v) => onPrices({ ...prices, [key]: { ...prices[key], [t]: v } })} />
              ))}
            </div>
          ))}
        </div>
      </section>

      <section className="card-block">
        <h2>Кухня и купе</h2>
        {num(other)}
      </section>

      <section className="card-block">
        <h2>Работа и наценка</h2>
        {num(business)}
      </section>

      <button className="link" onClick={() => confirm('Вернуть цены по умолчанию?') && onPrices(defaultPrices)}>Сбросить цены по умолчанию</button>
    </div>
  );
}
