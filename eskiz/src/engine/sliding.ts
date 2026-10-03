import {z} from 'zod';
export const slidingSource='https://ads-decor.ua/wp-content/uploads/%D0%A1%D0%B8%D1%81%D1%82%D0%B5%D0%BC%D0%B0-Brand.pdf';
// ADS BRAND, manufacturer table 1, page 6: overlap, glass-width deduction,
// board-width deduction, horizontal-profile deduction. All dimensions in mm.
export const slidingProfiles={'020':[33,38,35,50],'021':[28,32,29,45],'022':[41,37,35,50],'07':[41,37,35,50],'119':[26,37,35,50],'117':[50,87,85,100],'120':[41,69,67,82],'06':[32,51,49,64]} as const;
export const slidingSchema=z.object({profile:z.enum(['020','021','022','07','119','117','120','06']),count:z.union([z.literal(2),z.literal(3)]),reserve:z.number().min(80).max(200),railAllowance:z.number().min(0).max(10),fills:z.array(z.enum(['mirror','glass','board'])).min(2).max(3)}).refine(s=>s.fills.length===s.count,{message:'Количество заполнений не совпадает с числом дверей'});
export type Sliding=z.infer<typeof slidingSchema>;
export const defaultSliding:Sliding={profile:'020',count:2,reserve:90,railAllowance:0,fills:['mirror','mirror']};
export const fillNames={mirror:'Зеркало 4 мм',glass:'Стекло 4 мм',board:'Плита 10 мм'};
const r=(v:number)=>Math.round(v*100)/100;
export function calculateSliding(m:{width:number;height:number;depth:number;sliding?:Sliding},t:number){
 const s=m.sliding,errors:string[]=[];
 if(!s||!slidingSchema.safeParse(s).success||![m.width,m.height,m.depth,t].every(v=>Number.isFinite(v)&&v>0))return {errors:['Проверьте параметры шкафа-купе.'],openingWidth:0,openingHeight:0,doorWidth:0,doorHeight:0,profiles:[],fills:[],hardware:[]};
 const [overlap,glassDeduct,boardDeduct,horizontalDeduct]=slidingProfiles[s.profile];
 const openingWidth=r(m.width-2*t),openingHeight=r(m.height-2*t),doorHeight=r(openingHeight-43),doorWidth=r((openingWidth+overlap*(s.count-1))/s.count);
 if(doorWidth<500||doorWidth>1300||doorHeight<300||doorHeight>3200)errors.push('ADS BRAND: допустимая створка 500–1300 мм шириной и 300–3200 мм высотой.');
 if(m.depth-s.reserve<100)errors.push('После отступа дверной системы остаётся меньше 100 мм глубины.');
 const profiles=[{name:'Верхняя направляющая 104',length:r(openingWidth-s.railAllowance),qty:1},{name:'Нижняя направляющая 308',length:r(openingWidth-s.railAllowance),qty:1},{name:`Вертикальный профиль ${s.profile}`,length:doorHeight,qty:2*s.count},{name:'Верхний горизонтальный профиль 02',length:r(doorWidth-horizontalDeduct),qty:s.count},{name:'Нижний горизонтальный профиль 01',length:r(doorWidth-horizontalDeduct),qty:s.count}];
 const fills=s.fills.map((kind,i)=>({door:i+1,kind,name:fillNames[kind],height:r(doorHeight-(kind==='board'?60:63)),width:r(doorWidth-(kind==='board'?boardDeduct:glassDeduct)),thickness:kind==='board'?10:4}));
 if(profiles.some(p=>p.length<=0)||fills.some(f=>f.height<=0||f.width<=0))errors.push('Получен неположительный размер профиля или заполнения.');
 const perimeter=fills.filter(f=>f.kind!=='board').reduce((a,f)=>a+2*(f.height+f.width)/1000,0);
 const mirrorArea=fills.filter(f=>f.kind==='mirror').reduce((a,f)=>a+f.height*f.width/1e6,0);
 const hardware=[{name:'Нижние ролики',qty:2*s.count,unit:'шт.'},{name:'Верхние ролики под выбранный профиль',qty:2*s.count,unit:'шт.'},{name:'Уплотнитель для заполнения 4 мм (чистый периметр)',qty:r(perimeter),unit:'м'},{name:'Защитная плёнка для зеркала (чистая площадь)',qty:r(mirrorArea),unit:'м²'},{name:'Щётка по двум вертикалям каждой двери (без запаса)',qty:r(2*s.count*doorHeight/1000),unit:'м'}];
 return {errors,openingWidth,openingHeight,doorWidth,doorHeight,profiles,fills,hardware};
}
export function slidingCsv(m:{name:string;width:number;height:number;depth:number;sliding?:Sliding},t:number){
 const c=calculateSliding(m,t);if(c.errors.length)throw Error(c.errors.join(' '));
 const rows:unknown[][]=[['Шкаф-купе ADS BRAND — спецификация для проверки, не файл импорта'],['Модуль',m.name],['Профиль',m.sliding!.profile],['Проём Ш×В, мм',c.openingWidth,c.openingHeight],['Створка Ш×В, мм',c.doorWidth,c.doorHeight],['Позиция','Длина / высота мм','Ширина мм','Количество','Единица'],...c.profiles.map(p=>[p.name,p.length,'',p.qty,'шт.']),...c.fills.map(f=>[`Дверь ${f.door}: ${f.name}`,f.height,f.width,1,'шт.']),...c.hardware.map(h=>[h.name,'','',h.qty,h.unit]),['Направляющие: припуск на подгонку, мм',m.sliding!.railAllowance],['Зеркало рассчитано по строке стеклянного заполнения; проверьте уплотнитель и фактический материал.'],['Крепёж, стопоры и доводчики подбираются по комплекту; присадка профилей не экспортируется.'],['Источник',slidingSource]];
 return '\ufeff'+rows.map(row=>row.map(v=>{let s=String(v).replace(/[\r\n]+/g,' ');if(/^[=+\-@\t]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"'}).join(';')).join('\r\n');
}
