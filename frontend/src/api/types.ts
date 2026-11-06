export type Role = 'owner' | 'member' | 'viewer'

export interface Membership {
  workspace_id: number
  name: string
  slug: string
  role: Role
}

export interface Me {
  user: { id: number; email: string; name: string; is_staff: boolean }
  workspaces: Membership[]
}

export interface Member {
  id: number
  user_id: number
  email: string
  name: string
  role: Role
}

export interface ApiKeyRow {
  id: number
  name: string
  prefix: string
  created_at: string
  last_used_at: string | null
  revoked: boolean
  key?: string
}

export interface Usage {
  today: { uploads: number; upload_bytes: number; api_requests: number }
  limits: { daily_uploads: number; max_upload_mb: number }
  history: Record<string, Record<string, number>>
}
