// The shapes of vshort/web.py's JSON, and the two ways to talk to it. Every message shown to Tai is Vietnamese.

export type RowState = 'queued' | 'running' | 'dead' | 'wait_brief' | 'wait_script' | 'error' | 'done' | 'idle'

/** The ten stages (vshort/stages.py): worked out by the server, the page only shows them. */
export type StageStatus = 'done' | 'running' | 'you' | 'error' | 'next'

export interface Eta {
  stop: string | null // label of the next stage that waits for Tai; null: none left
  until_stop: number | null // seconds until then (until done when stop is null)
  after_stop: number | null // seconds from Tai's approval to done; null when stop is null
}

/** A row's card: the stage it is at. */
export interface Progress {
  percent: number
  n: number // 1–10
  label: string
  status: StageStatus
  eta: Eta
  elapsed: number // seconds the stages have run so far, waits for Tai left out
}

export interface StageStep {
  step: string
  label: string
  status: 'done' | 'running' | 'next'
}

export interface Stage {
  key: string
  label: string
  what: string
  status: StageStatus
  seconds: number | null // done: time it took; running: time so far
  typical: number // seconds, median of the last finished runs
  overdue: boolean // running longer than typical
  steps: StageStep[] // only for the running stage
}

export interface StageView {
  stages: Stage[]
  current: number | null // index of the running / waiting / failed stage
  percent: number
  eta: Eta
}

export interface Row {
  slug: string
  topic: string // "" for a folder that has no run.json
  auto: boolean // the brief is not stopped for approval
  title: string // the publish title from cover/cover.json; "" until the video is finished
  state: RowState
  message: string // multi-line; for relogin rows, what to do
  step: string | null
  since: number | null // epoch seconds
  cost: number
  verdict: string | null // review.json: "Đạt" | "Cần sửa" | ...
  seconds: number | null // length of the finished video
  relogin: boolean // stopped because NotebookLM wants a new login
  removable: boolean // a topic still in the queue: no folder yet
  progress: Progress | null // running, waiting for Tai, failed or stopped
  cover: { name: string; v: number } | null // the card's picture: Tai's Gemini cover, else the composed one
  posted: boolean // sent to the CMS in use: it has an article there
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
  style: 'old' | 'neon' // run.json's style: a neon run has no English brief
  brief_vi: string | null
  brief_en: string | null
  brief_en_stale: boolean
  translation: TranslationRow[] | null
  length: { secs: number; min: number; max: number } | null // a neon script: final.mp4's estimated length, from the saved file
  proposed: ProposedRow[] | null
  review_md: string | null
  cost: CostEntry[]
  log_tail: string
  video: boolean // final.mp4 exists and is not being rewritten
  cover_v: number | null // mtime of cover/cover.json: the headline covers exist, ?v= on their address
  prompt: string | null // cover/prompt.txt: what Tai pastes into the Gemini app for a poster cover
  prompt_wide: string // pasted next in the same Gemini chat: the 16:9 one
  progress: StageView
  now: number // the server's clock, epoch seconds
  gemini: { '9x16': number | null; '16x9': number | null } // mtime of cover/gemini-<shape>.jpg, null when not uploaded
  cms: CmsInfo
}

export type CmsStepStatus = 'done' | 'running' | 'error' | 'next' | 'skip'

/** RUN/cms.json for the CMS in use (vshort/publish.py); {} before the first send. Never holds the token. */
export interface CmsRecord {
  state?: 'running' | 'done' | 'error' | 'left' | 'deleted' | 'unsure'
  message?: string
  steps?: { key: string; label: string; status: CmsStepStatus }[]
  article_id?: number | null
  workflow?: string // the CMS's name of the step the article is at
  proposal?: { publishId: string; video_sha: string } | null
  warning?: string | null // several lines
  link?: string | null // the article in CMS-Admin
}

export interface CmsInfo {
  configured: boolean // the server has its cms.toml and token
  missing: string[] // what it lacks, in Vietnamese
  env: 'dev' | 'prod' | null
  running: boolean // a `vshort cms` is sending this video now
  record: CmsRecord
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
