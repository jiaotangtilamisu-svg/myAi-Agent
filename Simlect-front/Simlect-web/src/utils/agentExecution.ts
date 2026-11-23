export type AgentName = 'supervisor' | 'aftersales' | 'shopping';
export type AgentPhase = 'ROUTING' | 'RUNNING' | 'SUCCESS' | 'ERROR' | 'TIMEOUT' | 'NEEDS_CLARIFICATION' | 'CANCELLED' | 'INVALID_RESULT';
export interface AgentExecution { agent: AgentName; status: AgentPhase }
const agents = new Set(['supervisor', 'aftersales', 'shopping']);
const phases = new Set(['ROUTING', 'RUNNING', 'SUCCESS', 'ERROR', 'TIMEOUT', 'NEEDS_CLARIFICATION', 'CANCELLED', 'INVALID_RESULT']);

export const validExecution = (value: unknown): value is AgentExecution => {
  if (!value || typeof value !== 'object') return false;
  const v = value as Record<string, unknown>;
  return typeof v.agent === 'string' && agents.has(v.agent) && typeof v.status === 'string' && phases.has(v.status);
};
export const mergeExecution = (old: AgentExecution[] = [], value: unknown): AgentExecution[] => {
  if (!validExecution(value)) return old;
  return [...old.filter(v => v.agent !== value.agent), { agent: value.agent, status: value.status }];
};
export const agentLabel = (value: string) => ({supervisor: '统一助手', aftersales: '售后 Agent', shopping: '导购 Agent'} as Record<string,string>)[value] || '未知 Agent';
export const phaseLabel = (value: string) => ({ROUTING:'识别需求',RUNNING:'正在查询',SUCCESS:'查询完成',ERROR:'查询失败',TIMEOUT:'查询超时',NEEDS_CLARIFICATION:'需要补充',CANCELLED:'已取消',INVALID_RESULT:'结果未通过校验'} as Record<string,string>)[value] || '待确认';
export const parseSupervisor = (raw: unknown) => {
  if (typeof raw !== 'string') return null;
  try {
    const value = JSON.parse(raw);
    if (value?.type !== 'SUPERVISOR_RESULT' || typeof value.intro !== 'string' || !Array.isArray(value.products) || !Array.isArray(value.agents) || !value.agents.every(validExecution)) return null;
    return value as { type: string; intro: string; products: Record<string,any>[]; agents: AgentExecution[]; status: string; canCreateCase?: boolean; showCaseProgress?: boolean };
  } catch { return null; }
};
