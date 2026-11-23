/** Consumer cards require verified business provenance, including historical replies. */
export function admittedProducts(rows: Record<string, any>[]): Record<string, any>[] {
  return rows.filter(p => (p.dataClass === 'REAL' && p.dataProvenance?.sourceType === 'LIVE_API'
    && ['price','sku','stock'].every(k => p.dataProvenance?.fieldSources?.[k] === 'LIVE_API'))
    || (p.dataClass==='LOCAL_STORE' && p.dataProvenance?.catalogueStatus==='LOCAL_STORE'
      && ['PUBLIC_DATASET','MANUAL'].includes(p.dataProvenance?.sourceType) && p.dataProvenance?.fieldSources?.price==='MANUAL'
      && p.dataProvenance?.fieldSources?.sku==='MANUAL' && ['MANUAL','SYNTHETIC'].includes(p.dataProvenance?.fieldSources?.stock)));
}
export function consumerReasons(value: unknown): string[] {
  return Array.isArray(value) ? [...new Set(value.filter((v): v is string => typeof v === 'string' && !!v.trim()))] : [];
}
