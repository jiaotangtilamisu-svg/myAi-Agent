export interface PolicyHit {
  chunkId: string; documentId: string; documentName: string; revision: number;
  section: string; text: string; source: string; originalUrl?: string; issuer?: string;
}
export interface PolicyAnswer { kind: string; messageId?: number; responseStatus?: string; modelFailureCode?: string; hits: PolicyHit[] }
export function parsePolicyAnswer(raw: unknown, messageId: number): PolicyAnswer | null {
  try {
    const value = typeof raw === 'string' ? JSON.parse(raw) : raw;
    if (!value || value.kind !== 'policy_answer' || !Array.isArray(value.hits)) return null;
    if (value.messageId != null && Number(value.messageId) !== messageId) return null;
    if (!value.hits.every((h: PolicyHit) => h && typeof h.chunkId === 'string' && typeof h.documentId === 'string'
      && Number.isInteger(h.revision) && typeof h.documentName === 'string' && typeof h.text === 'string' && typeof h.source === 'string')) return null;
    const hits=uniquePolicyHits(value.hits);
    return {...value,hits};
  } catch { return null; }
}
export function uniquePolicyHits(hits: PolicyHit[]): PolicyHit[] {
  const identities=new Map<string,PolicyHit>(),texts=new Set<string>(),result:PolicyHit[]=[];
  for(const h of hits){
    const id=JSON.stringify([h.documentId,h.revision,h.chunkId]);
    const previous=identities.get(id);
    if(previous && (previous.text!==h.text || previous.source!==h.source))throw new Error('政策证据不一致');
    identities.set(id,h);
    const textKey=JSON.stringify([h.documentId,h.revision,h.section,h.source,h.text.replace(/\s+/g,' ').trim()]);
    if(!texts.has(textKey)){texts.add(textKey);result.push(h)}
  }
  return result;
}
export function policyNotice(value: PolicyAnswer): string {
  if (value.responseStatus === 'EVIDENCE_UNAVAILABLE') return '政策检索未取得可用依据，不能据此给出规则结论。';
  if (value.responseStatus !== 'DEGRADED') return '政策原文与来源已保存；具体适用条件仍需核实。';
  if (value.modelFailureCode === 'MODEL_TIMEOUT') return '模型响应超时；以下展示已保存的政策原文，不包含模型判定。';
  if (value.modelFailureCode === 'MODEL_UPSTREAM_UNAVAILABLE') return '模型服务暂时繁忙；以下展示已保存的政策原文，不包含模型判定。';
  return '模型辅助分析不可用；以下展示已保存的政策原文，请人工核实。';
}
export function policySourceUrl(value?: string): string | undefined {
  try { const url = new URL(value || ''); return url.protocol === 'https:' ? url.href : undefined; } catch { return undefined; }
}
