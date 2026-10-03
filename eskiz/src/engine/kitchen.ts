import {z} from 'zod';
import type {Module} from './furniture';
export const kitchenSchema=z.object({kind:z.enum(['base','wall','tall','sink']),fronts:z.union([z.literal(1),z.literal(2)]),railWidth:z.number().min(50).max(200)});
export const moduleKinds={wardrobe:'Шкаф / шкаф-купе',base:'Нижняя тумба',wall:'Навесной шкаф',tall:'Кухонный пенал',sink:'Тумба под мойку'} as const;
export type ModuleKind=keyof typeof moduleKinds;
export function makeModule(kind:ModuleKind,id:string):Module{
 if(kind==='wardrobe')return {id,name:'Шкаф',width:1800,height:2400,depth:600,sections:3,shelves:4,doors:true,back:true};
 return {id,name:moduleKinds[kind],width:kind==='sink'?800:600,height:kind==='tall'?2100:720,depth:kind==='wall'?320:560,sections:1,shelves:kind==='sink'?0:kind==='tall'?4:kind==='wall'?2:1,doors:true,back:kind!=='sink',kitchen:{kind,fronts:kind==='sink'?2:1,railWidth:100}};
}
export function hasRails(m:Module){return m.kitchen?.kind==='base'||m.kitchen?.kind==='sink'}
export function frontCount(m:Module){return m.kitchen?.fronts??m.sections}
export function moduleLayout(modules:Module[]){
 let lower=0,upper=0;const gap=modules.some(m=>m.kitchen)?0:35;const depth=Math.max(0,...modules.map(m=>m.depth));
 const items=modules.map(m=>{const wall=m.kitchen?.kind==='wall';const x=m.positionX??(wall?upper:lower),y=m.elevation??(wall?1450:m.kitchen?100:0);if(wall)upper=Math.max(upper,x+m.width+gap);else lower=Math.max(lower,x+m.width+gap);return {m,x,y,z:depth-m.depth}});
 return {items,width:Math.max(0,...items.map(v=>v.x+v.m.width)),height:Math.max(0,...items.map(v=>v.y+v.m.height)),depth};
}
export function layoutCollisions(modules:Module[]){const {items}=moduleLayout(modules);const errors:string[]=[];for(let i=0;i<items.length;i++)for(let j=0;j<i;j++){const a=items[i],b=items[j];if(Math.min(a.x+a.m.width,b.x+b.m.width)-Math.max(a.x,b.x)>.01&&Math.min(a.y+a.m.height,b.y+b.m.height)-Math.max(a.y,b.y)>.01)errors.push(`Корпуса «${a.m.name}» и «${b.m.name}» пересекаются. Измените положение по горизонтали или высоту от пола.`)}return errors}
