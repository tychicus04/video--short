// The ten stages of one video (vshort/stages.py works them out; this only draws them): the head with the percent and
// the time left, and the list of stages with what each took, is taking or usually takes.
import { Check, Circle, Dot } from 'lucide-react'
import type { Row, Stage, StageView } from '@/api'
import { cn } from '@/lib/utils'
import { fmtClock, fmtClockLength, fmtDuration, fmtLeft } from '@/status'

const minutes = (s: number) => (s < 60 ? 'dưới 1 phút' : `${Math.round(s / 60)} phút`)
const lower = (s: string) => s.charAt(0).toLowerCase() + s.slice(1)

/** Machine time so far: what the stages took, the waits for Tai left out. */
const elapsed = (view: StageView) => view.stages.reduce((a, s) => a + (s.seconds ?? 0), 0)

function Box({ title, value, extra }: { title: string; value: string; extra?: string }) {
  return (
    <div className="rounded-lg bg-muted px-4 py-3">
      <div className="text-sm text-muted-foreground">{title}</div>
      <div className="text-lg font-semibold">
        {value} {extra && <span className="text-sm font-medium text-muted-foreground">· {extra}</span>}
      </div>
    </div>
  )
}

export function ProgressHeader({ view, row }: { view: StageView; row: Row }) {
  const at = view.current == null ? null : view.stages[view.current]
  const { stop, until_stop, after_stop } = view.eta
  const ran = elapsed(view)
  const stopped = row.state === 'error' || row.state === 'dead'
  return (
    <section aria-label="Tiến độ chung" className="flex flex-wrap items-center gap-6 rounded-lg bg-card p-6">
      <div
        className="grid size-28 shrink-0 place-items-center rounded-full"
        style={{ background: `conic-gradient(var(--color-brand) ${view.percent * 3.6}deg, var(--secondary) 0)` }}
        role="img"
        aria-label={`Xong ${view.percent}%`}
      >
        <span className="grid size-[88px] place-items-center rounded-full bg-card text-[28px] leading-none font-bold">{view.percent}%</span>
      </div>
      <div className="flex min-w-0 flex-[1_1_300px] flex-col gap-1">
        {at && <div className="text-sm text-muted-foreground">Bước {view.current! + 1} trên 10</div>}
        <div className="text-[22px] leading-tight font-semibold">{at ? at.label : view.percent === 100 ? 'Xong cả 10 bước' : 'Chưa bắt đầu'}</div>
        {ran > 0 && <div className="text-muted-foreground">Đã chạy {fmtDuration(ran)}</div>}
      </div>
      {!stopped && at && (
        <div className="flex flex-[1_1_280px] flex-col gap-2.5">
          {at.status === 'you' ? (
            <Box title="Máy đang chờ bạn" value={at.label} />
          ) : stop ? (
            <Box title={`Tới lúc cần bạn ${lower(stop)}`} value={`còn ${fmtLeft(until_stop)}`} extra={until_stop != null ? fmtClock(until_stop) : undefined} />
          ) : (
            <Box title="Tới lúc xong" value={`còn ${fmtLeft(until_stop)}`} extra={until_stop != null ? fmtClock(until_stop) : undefined} />
          )}
          {stop && <Box title="Sau khi bạn duyệt, tới lúc xong" value={fmtLeft(after_stop)} />}
        </div>
      )}
    </section>
  )
}

function when(s: Stage, auto: boolean): string {
  switch (s.status) {
    case 'done':
      return s.seconds == null ? 'xong' : `xong · ${minutes(s.seconds)}`
    case 'running':
      if (s.seconds == null) return 'đang chạy'
      return `đang chạy ${fmtClockLength(s.seconds)} · ${s.overdue ? 'lâu hơn thường lệ' : `thường ~${minutes(s.typical)}`}`
    case 'you':
      return 'chờ bạn'
    case 'error':
      return 'dừng ở đây'
    default:
      return s.typical === 0 || (s.key === 'brief' && !auto) ? 'chờ bạn' : `~${minutes(s.typical)}`
  }
}

const DOT = {
  done: 'bg-ok text-[#0D2A1A]',
  running: 'border-3 border-brand bg-brand/15 text-foreground',
  you: 'border-2 border-wait bg-wait-bg text-wait',
  error: 'bg-err text-white',
  next: 'border-2 border-faint text-muted-foreground',
}
const WHEN = { done: 'text-ok', running: 'font-semibold text-brand-text', you: 'text-wait', error: 'text-err-text', next: 'text-muted-foreground' }
const STATUS_WORD = { done: 'xong', running: 'đang chạy', you: 'chờ bạn', error: 'lỗi', next: 'chưa tới' }

function Item({ s, n, last, auto }: { s: Stage; n: number; last: boolean; auto: boolean }) {
  const open = s.status === 'running' || s.status === 'you' || s.status === 'error'
  return (
    <li className="flex gap-4">
      <div className="flex w-9 shrink-0 flex-col items-center">
        <span className={cn('grid size-8 shrink-0 place-items-center rounded-full text-[13px] font-bold', DOT[s.status])}>
          {s.status === 'done' ? <Check className="size-4" strokeWidth={3} aria-hidden /> : n}
          <span className="sr-only">: {STATUS_WORD[s.status]}</span>
        </span>
        {!last && <span aria-hidden className={cn('min-h-4 w-0.5 flex-1', s.status === 'done' ? 'bg-ok/40' : 'bg-secondary')} />}
      </div>
      <div className={cn('min-w-0 flex-1', open ? 'mb-4 rounded-lg bg-muted px-4 py-3.5' : 'pt-1 pb-5')}>
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <span className="font-semibold">{s.label}</span>
          <span className={cn('text-sm', WHEN[s.status])}>{when(s, auto)}</span>
        </div>
        <div className="text-sm text-muted-foreground">{s.what}</div>
        {s.steps.length > 0 && (
          <ul className="mt-2.5 space-y-1.5 text-sm">
            {s.steps.map((u) => (
              <li key={u.step} className="flex items-center gap-2.5">
                {u.status === 'done' ? (
                  <Check className="size-4 shrink-0 text-ok" aria-label="xong" />
                ) : u.status === 'running' ? (
                  <Dot className="size-4 shrink-0 scale-[2] text-brand-text" aria-label="đang chạy" />
                ) : (
                  <Circle className="size-3 shrink-0 text-faint" aria-label="chưa tới" />
                )}
                <span className={u.status === 'next' ? 'text-muted-foreground' : 'text-foreground'}>{u.label}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </li>
  )
}

/** The ten stages, top to bottom. `compact`: the finished ones on one line, then only the one the video is at. */
export function StageList({ view, auto, compact = false }: { view: StageView; auto: boolean; compact?: boolean }) {
  if (compact) {
    const done = view.stages.filter((s) => s.status === 'done')
    const at = view.current == null ? null : view.stages[view.current]
    return (
      <section aria-label="Các bước" className="space-y-3 rounded-lg bg-card p-5">
        {done.length > 0 && (
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
            {done.map((s) => (
              <span key={s.key} className="inline-flex items-center gap-1">
                <Check className="size-3.5 text-ok" aria-label="xong" /> {s.label}
              </span>
            ))}
          </p>
        )}
        {at && (
          <ol className="list-none">
            <Item s={at} n={view.current! + 1} last auto={auto} />
          </ol>
        )}
        {view.current != null && view.current < 9 && (
          <p className="text-sm text-muted-foreground">Còn {9 - view.current} bước sau đó</p>
        )}
      </section>
    )
  }
  return (
    <ol className="list-none">
      {view.stages.map((s, i) => (
        <Item key={s.key} s={s} n={i + 1} last={i === view.stages.length - 1} auto={auto} />
      ))}
    </ol>
  )
}
