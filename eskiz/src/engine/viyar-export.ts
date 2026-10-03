import type {Part} from './furniture';
export const viyarImportHelp='https://www.viyar.pro/service/doc/?cid=dsp&s=details-import';
export type Orientation='horizontal'|'vertical';
export function viyarGroups(parts:Part[]){
 const groups=new Map<string,Part[]>();
 for(const p of parts){const key=JSON.stringify([p.catalogMaterial?.id??p.material,p.thickness]);groups.set(key,[...(groups.get(key)||[]),p]);}
 return [...groups].map(([id,parts],i)=>({id,index:i+1,parts,material:parts[0].material,thickness:parts[0].thickness}));
}
export function viyarEdges(parts:Part[]){
 const entries=new Map<string,{key:string;thickness:number;name:string}>();
 for(const p of parts)for(const thickness of p.edges)if(thickness>0){const key=JSON.stringify([p.catalogEdge?.id??'manual',thickness]);entries.set(key,{key,thickness,name:p.catalogEdge?.name??'Кромка выбрана вручную — уточните декор'});}
 return [...entries.values()].map((e,i)=>({...e,index:i+1}));
}
export function viyarIssues(parts:Part[]){
 const issues:string[]=[];
 for(const p of parts){
  if(p.stale)issues.push(`${p.name}: подтвердите устаревшие правки.`);
  if(p.grain==='Вдоль ширины')issues.push(`${p.name}: текстура вдоль ширины. Этот экспорт поддерживает текстуру вдоль длины или без направления.`);
  if(![p.cutLength,p.cutWidth,p.thickness,p.qty].every(v=>Number.isFinite(v)&&v>0)||!Number.isInteger(p.qty)||p.edges.some(v=>!Number.isFinite(v)||v<0))issues.push(`${p.name}: некорректные размеры или количество.`);
 }
 return [...new Set(issues)];
}
export function viyarCsv(parts:Part[],orientation:Orientation){
 if(!parts.length||viyarGroups(parts).length!==1)throw Error('В одном файле должен быть один материал одной толщины.');
 if(viyarIssues(parts).length)throw Error(viyarIssues(parts).join(' '));
 if(!['horizontal','vertical'].includes(orientation))throw Error('Укажите ориентацию длины на схеме ВіЯр.');
 const edges=viyarEdges(parts);
 const cell=(v:unknown)=>{let s=String(v).replace(/[\r\n\t]+/g,' ');if(/^[=+\-@]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};
 // Order is defined by ViyarPro: saw length, saw width, quantity, T, B, L, R, grain, name, layers.
 const rows=parts.map(p=>{
  const e=p.edges.map(t=>t===0?0:edges.find(e=>e.key===JSON.stringify([p.catalogEdge?.id??'manual',t]))!.index);
  const sides=orientation==='horizontal'?[e[1],e[0],e[2],e[3]]:[e[3],e[2],e[0],e[1]];
  return [p.cutLength,p.cutWidth,p.qty,...sides,p.grain==='Без направления'?'0':'1',`${p.module} / ${p.name} [${p.id}]`,1];
 });
 return '\ufeff'+rows.map(row=>row.map(cell).join(';')).join('\r\n')+'\r\n';
}
