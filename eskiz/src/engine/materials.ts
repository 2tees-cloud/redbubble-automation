import {z} from 'zod';
const supplierUrl=z.string().max(2000).refine(value=>{try{const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password&&['viyar.ua','www.viyar.ua','kronas.com.ua','www.kronas.com.ua'].includes(u.hostname)}catch{return false}},'Нужна HTTPS-ссылка на сайт поставщика');
export const stockLabels={in_stock:'В наличии',on_order:'Под заказ',out_of_stock:'Нет в наличии',discontinued:'Снят с производства',unknown:'Наличие не проверено'} as const;
export const materialSchema=z.object({id:z.string().max(100),supplier:z.enum(['viyar','kronas']),sku:z.string().max(100),name:z.string().max(300),category:z.string().max(80),brand:z.string().max(100),image:z.union([z.literal(''),supplierUrl]),url:supplierUrl,status:z.enum(['in_stock','on_order','out_of_stock','discontinued','unknown']),checkedAt:z.string().datetime({offset:true}),length:z.number().finite().positive().nullable(),width:z.number().finite().positive().nullable(),thickness:z.number().finite().positive().nullable(),surface:z.string().max(100),grain:z.string().max(100)});
export type Material=z.infer<typeof materialSchema>;
export const choicesSchema=z.object({body:materialSchema.optional(),front:materialSchema.optional(),back:materialSchema.optional(),edge:materialSchema.optional(),worktop:materialSchema.optional()});
export type Choices=z.infer<typeof choicesSchema>;
export type MaterialTarget=keyof Choices;
export const targetLabels:Record<MaterialTarget,string>={body:'Корпус и полки',front:'Фасады',back:'Задняя стенка',edge:'Кромка',worktop:'Столешница'};
export const materialLabel=(m:Material)=>`${m.name} [${m.supplier==='viyar'?'ВіЯр':'KRONAS'}: ${m.sku}]`;
export function canApply(m:Material,target:MaterialTarget){
 if(target==='edge')return m.category==='Кромка'&&m.thickness!==null&&m.thickness>0&&m.thickness<=3;
 if(target==='worktop')return m.category==='Столешницы';
 if(target==='back')return m.category==='ХДФ / ДВП'&&m.thickness!==null&&m.thickness>=3&&m.thickness<=10;
 return ['ЛДСП','МДФ панели'].includes(m.category)&&m.thickness!==null&&m.thickness>=10&&m.thickness<=30;
}
