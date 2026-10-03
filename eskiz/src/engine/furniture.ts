import {kitchenSchema,hasRails,frontCount,layoutCollisions} from './kitchen';
import {slidingSchema,calculateSliding} from './sliding';
import { z } from 'zod';
import {choicesSchema,materialLabel,canApply,type Material,type MaterialTarget} from './materials';
export const faceValues=['A','B','L1','L2','W1','W2'] as const;
export const holeSchema=z.object({id:z.string().min(1).max(100),face:z.enum(faceValues),x:z.number().min(0).max(4000),y:z.number().min(0).max(4000),diameter:z.number().min(1).max(100),depth:z.number().positive().max(4000),through:z.boolean()});
export type Hole=z.infer<typeof holeSchema>;
export type Face=Hole['face'];
export const editSchema=z.object({signature:z.string().max(2000),name:z.string().min(1).max(100),length:z.number().min(10).max(4000),width:z.number().min(10).max(3000),thickness:z.number().min(3).max(50),material:z.string().min(1).max(400),edges:z.tuple([z.number().min(0).max(3),z.number().min(0).max(3),z.number().min(0).max(3),z.number().min(0).max(3)]),grain:z.enum(['Вдоль длины','Вдоль ширины','Без направления']),holes:z.array(holeSchema).max(200).refine(h=>new Set(h.map(x=>x.id)).size===h.length)});
export type PartEdit=z.infer<typeof editSchema>;
export const moduleSchema=z.object({id:z.string().min(1).max(80),name:z.string().min(1).max(80),width:z.number().min(200).max(3000),height:z.number().min(200).max(3000),depth:z.number().min(150).max(1000),sections:z.number().int().min(1).max(6),shelves:z.number().int().min(0).max(12),doors:z.boolean(),back:z.boolean(),sliding:slidingSchema.optional(),kitchen:kitchenSchema.optional(),positionX:z.number().min(0).max(20000).optional(),elevation:z.number().min(0).max(3000).optional()});
export const projectSchema=z.object({version:z.literal(1),catalog:choicesSchema.optional(),finish:z.enum(['oak','walnut','white','graphite']).optional(),name:z.string().min(1).max(100),notes:z.string().max(5000),material:z.string().min(1).max(400),thickness:z.number().min(10).max(30),edge:z.number().min(0).max(3),gap:z.number().min(1).max(6),shelfClearance:z.number().min(0).max(5),shelfRecess:z.number().min(0).max(80),modules:z.array(moduleSchema).min(1).max(20).refine(ms=>new Set(ms.map(m=>m.id)).size===ms.length),partEdits:z.record(editSchema).optional(),image:z.string().max(9000000).refine(s=>s===''||/^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(s)).optional()});
export type Module=z.infer<typeof moduleSchema>;
export type Project=z.infer<typeof projectSchema>;
export type Part={id:string;module:string;name:string;length:number;width:number;cutLength:number;cutWidth:number;qty:number;thickness:number;material:string;edges:[number,number,number,number];grain:string;edgeM:number;signature:string;holes:Hole[];customized?:boolean;stale?:boolean;catalogMaterial?:Material;catalogEdge?:Material};
export const defaultProject:Project={version:1,name:'Шкаф с полками',notes:'',material:'ЛДСП — декор не выбран',thickness:18,edge:1,gap:2,shelfClearance:1,shelfRecess:20,modules:[{id:'m1',name:'Шкаф',width:1800,height:2400,depth:600,sections:3,shelves:4,doors:true,back:true}]};
export const round=(n:number)=>Math.round(n*100)/100;
export function calculate(p:Project){
 const parts:Part[]=[];const errors:string[]=[];const warnings:string[]=[];
 const valid=projectSchema.safeParse(p);if(!valid.success)return {parts,errors:['Проверьте размеры и количество секций: значения вне допустимых границ.'],warnings};
 const t=p.thickness,e=p.edge;
 errors.push(...layoutCollisions(p.modules));
 for(const [target,choice] of Object.entries(p.catalog||{}))if(choice&&!canApply(choice,target as MaterialTarget))errors.push(`Материал не подходит к назначению: ${target}. Перевыберите его в каталоге.`);
 if(errors.length)return {parts,errors,warnings};
 if(p.catalog?.body&&(p.catalog.body.thickness!==t||materialLabel(p.catalog.body)!==p.material))errors.push('Материал корпуса не соответствует выбранному артикулу. Перевыберите материал.');
 if(p.catalog?.edge&&p.catalog.edge.thickness!==e)errors.push('Толщина кромки не соответствует выбранному артикулу.');
 for(const m of p.modules){
 if(m.kitchen){if(m.sliding||m.sections!==1)errors.push(`${m.name}: кухонный модуль должен иметь одну секцию без дверей-купе.`);if(m.kitchen.kind==='sink'&&(m.back||m.shelves!==0))errors.push(`${m.name}: шаблон мойки не допускает полок и задней стенки.`);if(hasRails(m)&&m.kitchen.railWidth*2>=m.depth)errors.push(`${m.name}: две верхние планки перекрывают всю глубину.`);warnings.push(`${m.name}: высота задана для корпуса. Опоры, навесы, цоколь, столешница и вырезы не входят в деталировку.`);if(m.kitchen.kind==='sink')warnings.push(`${m.name}: проверьте положение чаши мойки и коммуникаций относительно верхних планок.`);}
 if(m.sliding)errors.push(...calculateSliding(m,t).errors.map(e=>`${m.name}: ${e}`));const reserve=m.sliding?.reserve??0;const insideH=m.height-2*t;const bay=(m.width-(m.sections+1)*t)/m.sections;
 if(bay<100||insideH-(m.shelves*t)<(m.shelves+1)*50||m.depth-reserve-p.shelfRecess<100){errors.push(`${m.name}: недостаточно места для секций или полок.`);continue;}
 const add=(name:string,l:number,w:number,qty:number,edges:[number,number,number,number],mat=p.material,th=t,grain='Вдоль длины')=>{
  const source=name==='Накладной фасад'?(p.catalog?.front??p.catalog?.body):name==='Накладная задняя стенка'?p.catalog?.back:p.catalog?.body;
  if(source){mat=materialLabel(source);th=source.thickness??th;grain=/без напрям|без направ/i.test(source.grain)?'Без направления':grain;}
  const role:Record<string,string>={'Верхняя соединительная планка':'rail','Боковина':'side','Дно / крышка между боковинами':'horizontal','Вертикальная перегородка':'divider','Съёмная полка':'shelf','Накладной фасад':'door','Накладная задняя стенка':'back'};
  for(let i=0;i<qty;i++){
   const partName=name==='Боковина'?(i===0?'Боковина левая':'Боковина правая'):name==='Дно / крышка между боковинами'?(i===0?'Дно':'Крышка'):qty>1?`${name} ${i+1}`:name;
   const id=`${m.id}:${role[name]}:${i+1}`;
   const signature=JSON.stringify({w:m.width,h:m.height,d:m.depth,n:m.sections,s:m.shelves,doors:m.doors,back:m.back,t,e,g:p.gap,c:p.shelfClearance,r:p.shelfRecess,...(m.kitchen?{kitchen:m.kitchen}:{}),...(m.sliding?{slidingReserve:reserve}:{}),l,w2:w,th,mat,...(source?{catalogId:source.id}:{}),...(p.catalog?.edge&&edges.some(v=>v>0)?{edgeId:p.catalog.edge.id}:{})});
   let part:Part={id,module:m.name,name:partName,length:round(l),width:round(w),cutLength:0,cutWidth:0,qty:1,thickness:th,material:mat,edges:[...edges],grain,edgeM:0,signature,holes:[],catalogMaterial:source,catalogEdge:edges.some(v=>v>0)?p.catalog?.edge:undefined};
   const edit=p.partEdits?.[id];
   if(edit){if(edit.signature===signature){part={...part,...edit,id,module:m.name,customized:true};}else{part.stale=true;errors.push(`${m.name}, ${partName}: размеры конструкции изменились. Перепроверьте сохранённые правки и отверстия.`);}}
   if(part.material!==mat||part.thickness!==th)part.catalogMaterial=undefined;
   if(part.edges.some(v=>v>0&&v!==p.catalog?.edge?.thickness))part.catalogEdge=undefined;
   part.cutLength=round(part.length-part.edges[2]-part.edges[3]);part.cutWidth=round(part.width-part.edges[0]-part.edges[1]);
   part.edgeM=round(((part.edges[0]>0?part.length:0)+(part.edges[1]>0?part.length:0)+(part.edges[2]>0?part.width:0)+(part.edges[3]>0?part.width:0))/1000);
   errors.push(...validatePart(part).map(x=>`${m.name}, ${partName}: ${x}`));parts.push(part);
  }
 };
 add('Боковина',m.height,m.depth,2,[e,0,0,0]);
 add('Дно / крышка между боковинами',m.width-2*t,m.depth,hasRails(m)?1:2,[e,0,0,0]);
 if(hasRails(m))add('Верхняя соединительная планка',m.width-2*t,m.kitchen!.railWidth,2,[e,e,0,0]);
 add('Вертикальная перегородка',insideH,m.depth-reserve,m.sections-1,[e,0,0,0]);
 add('Съёмная полка',bay-2*p.shelfClearance,m.depth-reserve-p.shelfRecess,m.shelves*m.sections,[e,0,0,0]);
 if(m.doors&&!m.sliding)add('Накладной фасад',m.height-2*p.gap,(m.width-(frontCount(m)+1)*p.gap)/frontCount(m),frontCount(m),[e,e,e,e]);
 if(m.back)add('Накладная задняя стенка',m.height-2,m.width-2,1,[0,0,0,0],'HDF — декор не выбран',3,'Без направления');
 if(bay>800)warnings.push(`${m.name}: пролёт полки ${round(bay)} мм — проверить прогиб и усиление.`);
 if(m.doors&&!m.sliding&&(m.height>2200||(m.width-(frontCount(m)+1)*p.gap)/frontCount(m)>600))warnings.push(`${m.name}: проверить допустимые габариты и массу фасадов по выбранным петлям.`);
 }
 for(const part of parts){const sheet=part.catalogMaterial;if(sheet?.length&&sheet.width){const fits=part.cutLength<=sheet.length&&part.cutWidth<=sheet.width;const rotated=part.grain==='Без направления'&&part.cutWidth<=sheet.length&&part.cutLength<=sheet.width;if(!fits&&!rotated)warnings.push(`${part.module}, ${part.name}: деталь не помещается в лист ${sheet.length} × ${sheet.width} мм с выбранной текстурой.`);}else if(part.cutLength>2800||part.cutWidth>2070)warnings.push(`${part.module}, ${part.name}: проверьте формат листа и направление текстуры.`);if(part.catalogEdge?.width&&part.catalogEdge.width<part.thickness)warnings.push(`${part.name}: выбранная кромка уже толщины детали.`);}
 const orphanIds=Object.keys(p.partEdits||{}).filter(id=>!parts.some(x=>x.id===id));
 if(orphanIds.length)errors.push(`Сохранены правки ${orphanIds.length} удалённых деталей. Удалите неиспользуемые правки перед экспортом.`);
 return {parts,errors,warnings};
}
export function csv(parts:Part[]){const cell=(x:unknown)=>{let s=String(x);if(/^[=+\-@\t\r]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};return '\ufeff'+[['ЧЕРНОВИК: не формат импорта KRONAS / ViyarPro'],['Модуль','Деталь','Кол-во','Готовая длина мм','Готовая ширина мм','Заготовка длина мм','Заготовка ширина мм','Толщина мм','Материал','Кромка L1 мм','Кромка L2 мм','Кромка W1 мм','Кромка W2 мм','Текстура','Отверстия, шт.','ID детали','Поставщик','Артикул материала','Ссылка на материал','Артикул кромки'],...parts.map(x=>[x.module,x.name,x.qty,x.length,x.width,x.cutLength,x.cutWidth,x.thickness,x.material,...x.edges,x.grain,x.holes.length,x.id,x.catalogMaterial?.supplier??'',x.catalogMaterial?.sku??'',x.catalogMaterial?.url??'',x.catalogEdge?.sku??''])].map(row=>row.map(cell).join(';')).join('\r\n');}

export const faceNames:Record<Face,string>={A:'A — лицевая пласть',B:'B — оборотная пласть',L1:'L1 — длинный торец 1',L2:'L2 — длинный торец 2',W1:'W1 — короткий торец 1',W2:'W2 — короткий торец 2'};
export function faceSize(p:Pick<Part,'length'|'width'|'thickness'>,face:Face){return face==='A'||face==='B'?{x:p.length,y:p.width,depth:p.thickness}:face==='L1'||face==='L2'?{x:p.length,y:p.thickness,depth:p.width}:{x:p.width,y:p.thickness,depth:p.length};}
export function validatePart(p:Pick<Part,'length'|'width'|'thickness'|'edges'|'holes'>){
 const errors:string[]=[];
 if(p.length-p.edges[2]-p.edges[3]<=0||p.width-p.edges[0]-p.edges[1]<=0)errors.push('кромка превышает размеры детали.');
 for(let i=0;i<p.holes.length;i++){
  const h=p.holes[i],check=holeSchema.safeParse(h);if(!check.success){errors.push(`отверстие ${i+1}: недопустимые параметры.`);continue;}
  const f=faceSize(p,h.face),r=h.diameter/2;
  if(h.x-r<0||h.y-r<0||h.x+r>f.x||h.y+r>f.y)errors.push(`отверстие ${i+1}: выходит за границу поверхности ${h.face}.`);
  if(!h.through&&h.depth>=f.depth)errors.push(`отверстие ${i+1}: глухая глубина должна быть меньше ${f.depth} мм.`);
  for(let j=0;j<i;j++){const b=p.holes[j];if(b.face===h.face&&Math.hypot(b.x-h.x,b.y-h.y)<(b.diameter+h.diameter)/2)errors.push(`отверстия ${j+1} и ${i+1} пересекаются на поверхности ${h.face}.`);}
 }
 return errors;
}
export function drillingCsv(parts:Part[]){const q=(v:unknown)=>{let s=String(v);if(/^[=+\-@\t\r]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};return '\ufeff'+[['ЧЕРНОВИК. Локальные координаты выбранной поверхности, от нижнего левого угла готовой детали. Не CNC и не импорт KRONAS/ViyarPro.'],['ID детали','Поверхность','X мм','Y мм','Диаметр мм','Глубина мм','Сквозное'],...parts.flatMap(p=>p.holes.map(h=>[p.id,h.face,h.x,h.y,h.diameter,h.through?faceSize(p,h.face).depth:h.depth,h.through?'Да':'Нет']))].map(r=>r.map(q).join(';')).join('\r\n');}
