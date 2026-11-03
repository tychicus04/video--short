// The shapes of vshort/web.py's JSON, and the two ways to talk to it. Every message shown to Tai is Vietnamese.

export type RowState = 'queued' | 'running' | 'dead' | 'wait_brief' | 'wait_script' | 'error' | 'done' | 'idle'

export interface Row {
  slug: string
  topic: string // "" for a folder that has no run.json
  auto: boolean // the brief is not stopped for approval
  state: RowState
  message: string // multi-line; for relogin rows, what to do
  step: string | null
  since: number | null // epoch seconds
  cost: number
  verdict: string | null // review.json: "Đạt" | "Cần sửa" | ...
  seconds: number | null // length of the finished video
  relogin: boolean // stopped because NotebookLM wants a new login
  removable: boolean // a topic still in the queue: no folder yet
}

export interface State {
  rows: Row[]
  relogin: string[] // slugs the queue is waiting on
  can_write: boolean
  token_set: boolean // false: the server has no access-code file, nobody can write
  max_running: number
}

export interface CostEntry {
  step: string
  agent: string
  seconds: number
  cost_usd: number
  models: string[]
  ok: boolean
}

export interface TranslationRow {
  id: number
  en: string
  phrases: string // Vietnamese, "|" between subtitle chunks
  note: string
}

export interface ProposedRow {
  id: number
  phrases: string
  note: string
}

export interface Detail {
  row: Row
  locked: boolean // a live `vshort auto` has the run: nothing can be edited
  brief_vi: string | null
  brief_en: string | null
  brief_en_stale: boolean
  translation: TranslationRow[] | null
  proposed: ProposedRow[] | null
  review_md: string | null
  cost: CostEntry[]
  log_tail: string
  video: boolean // final.mp4 exists and is not being rewritten
}

/** `error` is the Vietnamese message; `data` the parsed body, e.g. {errors: [...]} of a 400 from /api/queue. */
export class ApiError extends Error {
  status: number
  error: string
  data: any
  constructor(status: number, error: string, data: any = null) {
    super(error)
    this.status = status
    this.error = error
    this.data = data
  }
}

/** The message to show for anything thrown by getState/getRun/post. */
export const errorMessage = (e: unknown) => (e instanceof ApiError ? e.error : 'Có lỗi không rõ')

const noReply = (status: number) =>
  status === 502 || status === 503 || status === 504 ? 'Máy chủ không trả lời' : `Có lỗi (mã ${status})`

let lostAccess: (() => void) | null = null
/** Called when a write is refused with 403 (the access code is missing or was changed): App refreshes the state, so the code box shows again. */
export const onAccessLost = (fn: (() => void) | null) => {
  lostAccess = fn
}

const READ_TIMEOUT_MS = 10_000 // a read that takes longer is given up, so the 5-second refresh can try again and the failure is shown

async function call(path: string, init?: RequestInit): Promise<any> {
  let text: string
  let r: Response
  try {
    // only reads are given a deadline: a write may wait for an agent for a minute or two
    r = await fetch(path, { cache: 'no-store', signal: init?.method ? undefined : AbortSignal.timeout(READ_TIMEOUT_MS), ...init })
    text = await r.text() // not r.json(): login, remove, resume, approve... answer 204 with nothing in it. The deadline covers the body too.
  } catch {
    throw new ApiError(0, 'Không kết nối được máy chủ') // down, unreachable, or too slow
  }
  let data: any = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    /* not JSON: a proxy's HTML error page */
  }
  if (!r.ok) {
    const lost = r.status === 403 && init?.method === 'POST' && path !== '/api/login' // on /api/login a 403 is just a wrong code
    if (lost) lostAccess?.()
    const error = lost ? 'Mã truy cập không còn đúng, nhập lại mã' : typeof data?.error === 'string' ? data.error : noReply(r.status)
    throw new ApiError(r.status, error, data)
  }
  return data
}

export const getState = (): Promise<State> => call('/api/state')

export const getRun = (slug: string): Promise<Detail> => call(`/api/runs/${encodeURIComponent(slug)}`)

/** POST a JSON body. Resolves with the parsed reply, or null when the reply has no body (204). Throws ApiError. */
export const post = (path: string, body: unknown = {}): Promise<any> =>
  call(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
