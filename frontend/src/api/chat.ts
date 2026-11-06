import { api } from './client'

export interface Citation {
  document_id: number
  document: string
  page: number
  bbox: [number, number, number, number]
  kind: string
  quote: string
}

export interface AskResult {
  conversation_id: number
  answer: string
  grounded: boolean
  citations: Citation[]
  retrieved: number
  reason?: string
}

export const ask = (ws: number, question: string, conversationId?: number) =>
  api<AskResult>(`/workspaces/${ws}/chat/ask/`, {
    method: 'POST',
    json: { question, conversation_id: conversationId },
  })

/** Hash link that opens the document page with the cited passage highlighted. */
export const citationHref = (c: Citation) =>
  `#/documents/${c.document_id}?page=${c.page}&hl=${c.bbox.join(',')}`
