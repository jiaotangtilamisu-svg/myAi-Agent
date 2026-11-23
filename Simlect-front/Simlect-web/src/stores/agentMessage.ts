import { ref } from 'vue';
import { defineStore } from 'pinia';
import type { AgentExecution } from '@/utils/agentExecution';

export interface AgentWsMessage {
  agentStatus?: AgentExecution;
  messageId?: number | string;
  userMessage?: string;
  assistantMessage?: string;
  bizType?: string;
  bizData?: string;
  errorCode?: string;
  outPutType?: number;
  userId?: string;
}

export const useAgentMessageStore = defineStore('agentMessage', () => {
  const message = ref<AgentWsMessage | null>(null);

  const onMessage = (payload: AgentWsMessage) => {
    message.value = payload;
  };

  const clearMessage = () => {
    message.value = null;
  };

  return { message, onMessage, clearMessage };
});
