// The page of one video (#/r/<slug>). It reads the video every 5 seconds, except while Tai has edits not saved, and shows the
// page that fits the state: brief to approve, translation to approve, the finished video, a failure, or just how it is going.
import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowLeft, Loader2, WifiOff } from 'lucide-react'
import { ApiError, errorMessage, getRun, type Detail, type Row } from '@/api'
import { BriefReview } from '@/BriefReview'
import { Failed } from '@/Failed'
import { Finished } from '@/Finished'
import { ScriptReview } from '@/ScriptReview'
import { LogTail, Message, type Ctx } from '@/runKit'
import { ProgressHeader, StageList } from '@/Stages'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { StatusBadge, fmtAgo, money } from '@/status'
import { cn } from '@/lib/utils'

const REFRESH_MS = 5000

/** The video read now and every 5 seconds. Same rules as App's list: one read out at a time, an old answer never replaces a newer one, a failed read keeps the last good data. */
function useRun(slug: string, holding: { current: boolean }) {
  const [d, setD] = useState<Detail | null>(null)
  const [failed, setFailed] = useState('')
  const [gone, setGone] = useState(false)
  const latest = useRef(0)
  const pending = useRef(0)

  const read = useCallback(async () => {
    const mine = ++latest.current
    pending.current++
    try {
      const x = await getRun(slug)
      if (mine !== latest.current) return
      setD(x)
      setFailed('')
      setGone(false)
    } catch (e) {
      if (mine !== latest.current) return
      setFailed(errorMessage(e))
      setGone(e instanceof ApiError && e.status === 404)
    } finally {
      pending.current--
    }
  }, [slug])

  useEffect(() => {
    // edits not saved: a refresh must not put the file's text over the page Tai is typing in
    const poll = () => document.hidden || pending.current || holding.current || read()
    read()
    const tick = setInterval(poll, REFRESH_MS)
    document.addEventListener('visibilitychange', poll)
    return () => {
      clearInterval(tick)
      document.removeEventListener('visibilitychange', poll)
    }
  }, [read, holding])

  return { d, failed, gone, read }
}

/** A video that is queued, running or never started: the ten stages, what it is, and the log. */
function Progress({ c }: { c: Ctx }) {
  const { row, log_tail, progress } = c.d
  if (row.removable)
    return (
      <Card size="sm">
        <CardContent className="text-muted-foreground">Chủ đề này đang xếp hàng, chưa có thư mục. Tới lượt thì máy chủ mới bắt đầu.</CardContent>
      </Card>
    )
  const facts: [string, string][] = [
    ['Chủ đề', row.topic || '—'],
    ['Duyệt brief', row.auto ? 'Bỏ qua, chạy thẳng' : 'Chờ bạn duyệt'],
    ['Chi phí Claude', `${money(row.cost)} tới giờ`],
    ['Cập nhật', row.since != null ? fmtAgo(row.since) : '—'],
  ]
  return (
    <div className="space-y-6">
      <ProgressHeader view={progress} row={row} />
      <div className="flex flex-wrap items-start gap-6">
        <section aria-labelledby="steps-h" className="min-w-0 flex-[999_1_560px] rounded-lg bg-card p-6">
          <h2 id="steps-h" className="mb-4 text-lg font-semibold">
            Từng bước
          </h2>
          <StageList view={progress} auto={row.auto} />
        </section>
        <aside className="flex min-w-0 flex-[1_1_300px] flex-col gap-4">
          <section aria-labelledby="info-h" className="rounded-lg bg-card p-5">
            <h2 id="info-h" className="mb-3 font-semibold">
              Thông tin
            </h2>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2.5 text-sm">
              {facts.map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-muted-foreground">{k}</dt>
                  <dd className="[overflow-wrap:anywhere]">{v}</dd>
                </div>
              ))}
            </dl>
            {row.message.trim() && <Message text={row.message} className="mt-3 rounded-lg bg-muted p-3 text-muted-foreground" />}
          </section>
          <LogTail text={log_tail} />
          <p className="rounded-lg bg-card p-5 text-sm text-muted-foreground">
            Thời gian dự kiến lấy trung vị của 5 video xong gần nhất cho từng bước; chưa đủ thì dùng số ước sẵn.
          </p>
        </aside>
      </div>
    </div>
  )
}

/** Where a video that waits for Tai or stopped is: the head and the stage it is at, above the page for it. */
function Where({ c }: { c: Ctx }) {
  return (
    <div className="space-y-4">
      <ProgressHeader view={c.d.progress} row={c.d.row} />
      <StageList view={c.d.progress} auto={c.d.row.auto} compact />
    </div>
  )
}

export function RunDetail({
  slug,
  canWrite,
  fallback,
  refreshState,
}: {
  slug: string
  canWrite: boolean
  /** the Row the list already has: shown in the heading until this video's own read arrives */
  fallback: Row | undefined
  refreshState: () => unknown
}) {
  const holding = useRef(false)
  const { d, failed, gone, read } = useRun(slug, holding)
  const [busy, setBusy] = useState(false)

  const hold = useCallback((unsaved: boolean) => {
    holding.current = unsaved
  }, [])

  const write = useCallback(async <T,>(fn: () => Promise<T>): Promise<T> => {
    setBusy(true)
    try {
      return await fn()
    } finally {
      setBusy(false)
    }
  }, [])

  const reload = useCallback(async () => {
    refreshState() // the list and the header know of the change too
    await read()
  }, [read, refreshState])

  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (holding.current) {
        e.preventDefault()
        e.returnValue = '' // older Safari asks only when this is set
      }
    }
    addEventListener('beforeunload', warn)
    return () => removeEventListener('beforeunload', warn)
  }, [])

  const row = d?.row ?? fallback
  const c: Ctx | null = d && { slug, d, canWrite, locked: d.locked, busy, off: !canWrite || d.locked || busy, write, reload, hold }

  return (
    <div className="space-y-5">
      <Button asChild variant="ghost" size="sm" className="-ml-2">
        <a href="#/">
          <ArrowLeft /> Danh sách
        </a>
      </Button>

      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <h1 className={cn('text-2xl leading-tight font-bold sm:text-[28px]', row?.title ? '[overflow-wrap:anywhere]' : 'font-mono break-all')}>
            {row?.title || slug}
          </h1>
          {row && !gone && <StatusBadge state={row.state} />}
        </div>
        {row?.title && <p className="font-mono text-xs break-all text-muted-foreground">{slug}</p>}
        {row?.topic && !gone && <p className="text-sm text-muted-foreground [overflow-wrap:anywhere]">{row.topic}</p>}
      </header>

      {gone ? (
        <p className="text-sm text-muted-foreground">Không có video này. Có thể nó đã bị gỡ khỏi hàng đợi.</p>
      ) : (
        <>
          {failed && (
            <div role="alert" className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              <WifiOff className="size-3.5 shrink-0" />
              <span>
                {failed}
                {d ? ': đang hiện dữ liệu lần cập nhật cuối, trang sẽ tự thử lại' : ': trang sẽ tự thử lại sau vài giây'}
              </span>
            </div>
          )}

          {c?.locked && (
            <Alert className="border-sky-500/30 bg-sky-500/10 text-sky-200">
              <Loader2 className="animate-spin" />
              <AlertTitle>Video đang chạy</AlertTitle>
              <AlertDescription className="text-sky-100/80">Lúc này chưa sửa hay duyệt được. Trang tự làm mới, chạy xong thì sửa được.</AlertDescription>
            </Alert>
          )}

          {!c ? (
            <div className="space-y-3" aria-busy="true" aria-label="Đang tải">
              <Skeleton className="h-32 rounded-lg" />
              <Skeleton className="h-56 rounded-lg" />
            </div>
          ) : c.d.row.state === 'wait_brief' ? (
            <>
              <Where c={c} />
              <BriefReview c={c} />
            </>
          ) : c.d.row.state === 'wait_script' ? (
            <>
              <Where c={c} />
              <ScriptReview c={c} />
            </>
          ) : c.d.row.state === 'done' ? (
            <Finished c={c} />
          ) : c.d.row.state === 'error' || c.d.row.state === 'dead' ? (
            <>
              <Where c={c} />
              <Failed c={c} />
            </>
          ) : (
            <Progress c={c} />
          )}
        </>
      )}
    </div>
  )
}
