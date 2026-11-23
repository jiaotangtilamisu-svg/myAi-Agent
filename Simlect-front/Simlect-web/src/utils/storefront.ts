/** Presentation only. Facts and assigned prices remain untouched. */
export function diverseProducts<T extends {categoryId?: string}>(products: T[]): T[] {
  const groups = new Map<string, T[]>();
  for (const p of products) {
    const key=p.categoryId ?? '';
    if(!groups.has(key))groups.set(key,[]);
    groups.get(key)!.push(p);
  }
  const result:T[]=[];
  while(result.length<products.length){for(const rows of groups.values()){if(rows.length)result.push(rows.shift()!);}}
  return result;
}

export function visibleCatalogueRoots<T extends {categoryId: string;children?: {categoryId:string}[]}>(roots:T[],products:{categoryId?:string;pCategoryId?:string}[]):T[]{
  // The public reference catalogue has a complete navigable taxonomy. Do not
  // infer its navigation from the first page (which hides most departments).
  const referenceIds=['10001','10002','10003','10004','10005','10006','10007','10011','64617'];
  if(referenceIds.every(id=>roots.some(r=>r.categoryId===id))){
    return referenceIds.map(id=>roots.find(r=>r.categoryId===id)!);
  }
  if(!products.length)return roots;
  const ids=new Set(products.flatMap(p=>[p.categoryId,p.pCategoryId]).filter(Boolean));
  return roots.filter(root=>ids.has(root.categoryId)||root.children?.some(child=>ids.has(child.categoryId)));
}
