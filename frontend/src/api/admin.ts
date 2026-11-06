import { api } from './client'

export interface EvalSetMetrics {
  map50: number
  per_class_ap50: Record<string, number | null>
}

export interface ModelRow {
  id: number
  name: string
  is_active: boolean
  created_at: string
  n_feedback: number
  notes: string
  parent: string | null
  metrics: {
    previous?: Record<string, EvalSetMetrics>
    new?: Record<string, EvalSetMetrics>
    deltas?: Record<string, number>
    recommend_activate?: boolean
  }
}

export interface JobRow {
  id: number
  status: 'queued' | 'running' | 'done' | 'failed'
  epochs: number
  log: string
  result: ModelRow | null
}

export interface AdminModels {
  models: ModelRow[]
  jobs: JobRow[]
  feedback: { samples: number; corrected: number }
}

export const getModels = () => api<AdminModels>('/admin/models/')
export const startRetrain = (epochs: number) =>
  api<JobRow>('/admin/retrain/', { method: 'POST', json: { epochs } })
export const activateModel = (id: number) =>
  api<ModelRow>(`/admin/models/${id}/activate/`, { method: 'POST' })
export const rollbackModel = () => api<unknown>('/admin/models/rollback/', { method: 'POST' })
