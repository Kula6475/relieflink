import type { AgentMessage, MessageType } from "../domain";

export function structuredMessage(input: {
  id?: string;
  negotiationId: string;
  senderAgentId: string;
  recipientAgentId?: string;
  recipientScope?: string;
  messageType: MessageType;
  payload: Record<string, unknown>;
  parentMessageId?: string;
  agentRunId: string;
  explanation: string;
  expiresAt: string;
  createdAt?: string;
}): AgentMessage {
  if (!input.recipientAgentId && !input.recipientScope) {
    throw new Error("A structured message needs a recipient or recipient scope");
  }
  return {
    id: input.id ?? crypto.randomUUID(),
    negotiationId: input.negotiationId,
    senderAgentId: input.senderAgentId,
    recipientAgentId: input.recipientAgentId,
    recipientScope: input.recipientScope,
    messageType: input.messageType,
    payload: input.payload,
    parentMessageId: input.parentMessageId,
    agentRunId: input.agentRunId,
    explanation: input.explanation,
    status: "active",
    expiresAt: input.expiresAt,
    createdAt: input.createdAt ?? new Date().toISOString(),
  };
}
