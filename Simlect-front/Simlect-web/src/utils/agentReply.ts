import { normalizeAgentHistoryMessage, type AgentHistoryMessage } from './agentHistory.ts';

export function reconcileReply(target: AgentHistoryMessage, raw: Record<string, unknown>): boolean {
  if (!raw || raw.status == null || ![0, 2, 3, 4].includes(Number(raw.status))) return false;
  const reply = normalizeAgentHistoryMessage(raw);
  if (!reply.messageId || reply.messageId !== target.messageId) return false;
  if (![0, 2, 3, 4].includes(Number(reply.status))) return false;
  Object.assign(target, reply);
  return true;
}

export function applyTerminalReply(target: AgentHistoryMessage, raw: Record<string, unknown>, outputType: number): boolean {
  const persistenceError = raw.errorCode === 'DB_PERSISTENCE_FAILED' || raw.bizType === 'agent_persistence_error';
  return reconcileReply(target, { ...raw, status: persistenceError ? 4 : 2,
    assistantMessage: raw.assistantMessage || (outputType === 2 ? '处理失败，请稍后核实。' : target.assistantMessage) });
}
