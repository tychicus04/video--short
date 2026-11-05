// The home page's list of videos, in the sections of the approved sketch: what needs Tai, what is being made (stage, time
// left), the queue, the finished ones as a grid of covers, and the old folders. The server already sorts the rows.
import { useState, type ReactNode } from 'react'
import { Clapperboard, ClipboardCheck, Download, Loader2, TriangleAlert, Unplug, X } from 'lucide-react'
import { toast } from 'sonner'
import { errorMessage, post, type Progress, type Row } from '@/api'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { Tabs, firstLine, fmtAgo, fmtClockLength, fmtDuration, fmtLeft, money } from '@/status'

const href = (r: Row) => `#/r/${encodeURIComponent(r.slug)}`
const name = (r: Row) => r.title || r.topic || r.slug

function Section({ title, count, tone, aside, children }: { title: string; count: number; tone?: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">
          {title} <span className={cn('text-sm font-medium', tone ?? 'text-muted-foreground')}>· {count}</span>
        </h2>
        {aside}
      </div>
      {children}
    </section>
  )
}

/** The 10 stages as a row of segments: done green, the current one by its state, the rest grey. */
function Bar({ p }: { p: Progress }) {
  const now = { running: 'bg-brand', you: 'bg-wait', error: 'bg-err', done: 'bg-ok', next: 'bg-secondary' }[p.status]
  return (
    <div className="grid grid-cols-10 gap-1" aria-hidden>
      {Array.from({ length: 10 }, (_, i) => (
        <span key={i} className={cn('h-1.5 rounded-full', i < p.n - 1 ? 'bg-ok' : i === p.n - 1 ? now : 'bg-secondary')} />
      ))}
    </div>
  )
}

const NEED = {
  wait_brief: { icon: ClipboardCheck, why: 'Chờ bạn duyệt brief', go: 'Duyệt brief' },
  wait_script: { icon: ClipboardCheck, why: 'Chờ bạn duyệt bản dịch', go: 'Duyệt bản dịch' },
  error: { icon: TriangleAlert, why: '', go: 'Xem lỗi' },
  dead: { icon: Unplug, why: 'Dừng giữa chừng', go: 'Xem và chạy lại' },
} as const

function NeedsYou({ row }: { row: Row }) {
  const need = NEED[row.state as keyof typeof NEED]
  const bad = row.state === 'error' || row.state === 'dead'
  const at = row.progress ? ` ở bước ${row.progress.n}/10 · ${row.progress.label}` : ''
  const why =
    row.state === 'error'
      ? firstLine(row.message) || 'Không có lời nhắn, mở ra xem nhật ký'
      : row.state === 'dead'
        ? need.why + at
        : `${need.why} · ${fmtAgo(row.since) === 'vừa xong' ? 'vừa dừng' : `dừng ${fmtAgo(row.since)}`}`
  return (
    <div className={cn('flex flex-wrap items-center gap-4 rounded-lg p-4', bad ? 'bg-err/10' : 'bg-wait-bg')}>
      <span className={cn('grid size-12 shrink-0 place-items-center rounded-lg', bad ? 'bg-err/15 text-err-text' : 'bg-wait/15 text-wait')}>
        <need.icon className="size-5" />
      </span>
      <div className="min-w-0 flex-[1_1_320px]">
        <div className="font-semibold break-words">{name(row)}</div>
        <div className={cn('line-clamp-2 text-sm break-words', bad ? 'text-err-text' : 'text-wait')}>{why}</div>
      </div>
      <Button asChild className={bad ? 'bg-err-text text-background hover:bg-err-text/85' : 'bg-wait text-background hover:bg-wait/85'}>
        <a href={href(row)}>{need.go}</a>
      </Button>
    </div>
  )
}

function Making({ row }: { row: Row }) {
  const p = row.progress
  return (
    <a
      href={href(row)}
      className="flex gap-4 rounded-lg bg-card p-4 outline-none transition-colors hover:bg-[color-mix(in_oklch,var(--card),var(--foreground)_4%)] focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      <div className="flex w-24 shrink-0 flex-col items-center justify-center gap-0.5 rounded-lg bg-muted py-6">
        <span className="text-2xl font-bold">{p ? `${p.percent}%` : '…'}</span>
        <span className="text-xs text-muted-foreground">tiến độ</span>
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <span className="line-clamp-2 font-semibold break-words">{name(row)}</span>
        {p && (
          <>
            <span className="flex items-center gap-2 text-sm text-brand-text">
              <Loader2 className="size-3.5 shrink-0 animate-spin" aria-hidden />
              Bước {p.n}/10 · {p.label}
            </span>
            <Bar p={p} />
          </>
        )}
        <div className="mt-auto flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
          {p && p.elapsed > 0 && <span>Đã chạy {fmtDuration(p.elapsed)}</span>}
          {p?.eta.until_stop != null && (
            <span className="font-semibold text-foreground">
              còn {fmtLeft(p.eta.until_stop)}
              {p.eta.stop && ` tới lúc ${p.eta.stop.toLowerCase()}`}
            </span>
          )}
          <span>Claude {money(row.cost)}</span>
        </div>
      </div>
    </a>
  )
}

function Queued({ row, canWrite, refresh }: { row: Row; canWrite: boolean; refresh: () => void }) {
  const [busy, setBusy] = useState(false)

  async function remove() {
    setBusy(true)
    try {
      await post('/api/queue/remove', { slug: row.slug })
      toast.success(`Đã gỡ ${row.slug} khỏi hàng đợi`)
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
      refresh()
    }
  }

  return (
    <li className="flex items-center gap-3 px-4 py-3">
      <div className="min-w-0 flex-1">
        <a href={href(row)} className="line-clamp-2 font-semibold break-words outline-none hover:underline focus-visible:underline">
          {name(row)}
        </a>
        <div className="text-sm text-muted-foreground">
          Chờ tới lượt
          {row.since != null && ` · thêm ${fmtAgo(row.since)}`}
          {row.auto && ' · bỏ duyệt brief'}
        </div>
      </div>
      {row.removable && (
        <Button
          variant="outline"
          size="sm"
          className="shrink-0"
          disabled={!canWrite || busy}
          title={canWrite ? 'Gỡ chủ đề này khỏi hàng đợi' : 'Cần mã truy cập'}
          onClick={remove}
        >
          <X /> Gỡ
        </Button>
      )}
    </li>
  )
}

function Finished({ row }: { row: Row }) {
  const pic = row.cover && `/files/${encodeURIComponent(row.slug)}/${row.cover.name}?v=${row.cover.v}`
  const ago = fmtAgo(row.since)
  return (
    <article className="flex flex-col overflow-hidden rounded-lg bg-card">
      <a href={href(row)} className="relative block aspect-[3/4] bg-muted outline-none focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:ring-inset">
        {pic ? (
          <img src={pic} alt={`Ảnh bìa: ${name(row)}`} loading="lazy" className="size-full object-cover" />
        ) : (
          <span className="grid size-full place-items-center text-faint">
            <Clapperboard className="size-10" aria-label="Chưa có ảnh bìa" />
          </span>
        )}
        <span aria-hidden className="absolute inset-x-0 bottom-0 h-1/3 bg-[linear-gradient(to_bottom,rgba(33,35,44,0),rgba(33,35,44,.94)_75%)]" />
        {row.verdict && (
          <span
            className={cn(
              'absolute top-3 left-3 rounded-full px-2.5 py-1 text-xs font-semibold',
              row.verdict === 'Đạt' ? 'bg-[color-mix(in_srgb,var(--color-ok)_15%,var(--card))] text-ok' : 'bg-wait-bg text-wait',
            )}
          >
            Soát: {row.verdict}
          </span>
        )}
        {row.seconds != null && (
          <span className="absolute right-3 bottom-3 rounded-lg bg-background px-2 py-1 text-xs font-semibold">{fmtClockLength(row.seconds)}</span>
        )}
      </a>
      <div className="flex flex-1 flex-col gap-2 p-4">
        <a href={href(row)} className={cn('line-clamp-3 font-semibold break-words outline-none hover:underline focus-visible:underline', !row.title && 'font-mono text-sm')}>
          {row.title || row.slug}
        </a>
        <div className="text-sm text-muted-foreground">
          {money(row.cost)} · {ago === 'vừa xong' ? ago : `xong ${ago}`}
        </div>
        <div className="mt-auto flex gap-2 pt-1">
          <Button asChild className="flex-1">
            <a href={href(row)}>Đăng bài</a>
          </Button>
          <Button asChild variant="outline" size="icon">
            <a href={`/files/${encodeURIComponent(row.slug)}/final.mp4?download=1`} aria-label="Tải video về" title="Tải video về">
              <Download />
            </a>
          </Button>
        </div>
      </div>
    </article>
  )
}

export function RunList({ rows, canWrite, refresh }: { rows: Row[] | null; canWrite: boolean; refresh: () => void }) {
  const [filter, setFilter] = useState<'all' | 'fix'>('all')

  if (rows === null)
    return (
      <div className="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(min(100%,260px),1fr))]" aria-busy="true" aria-label="Đang tải danh sách">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="aspect-[3/4] rounded-lg" />
        ))}
      </div>
    )

  if (rows.length === 0)
    return <Card className="py-10 text-center text-muted-foreground">Chưa có video nào. Thêm chủ đề ở ô phía trên để bắt đầu.</Card>

  const of = (...states: Row['state'][]) => rows.filter((r) => states.includes(r.state))
  const needs = of('wait_brief', 'wait_script', 'error', 'dead')
  const making = of('running')
  const queued = of('queued')
  const done = of('done')
  const toFix = done.filter((r) => r.verdict && r.verdict !== 'Đạt')
  const shown = filter === 'fix' ? toFix : done
  const idle = of('idle')

  return (
    <div className="space-y-10">
      {needs.length > 0 && (
        <Section title="Cần bạn" count={needs.length} tone="text-wait">
          <div className="space-y-3">
            {needs.map((r) => (
              <NeedsYou key={r.slug} row={r} />
            ))}
          </div>
        </Section>
      )}

      {making.length > 0 && (
        <Section title="Đang tạo" count={making.length} tone="text-brand-text" aside={<span className="text-sm text-muted-foreground">Thời gian còn lại ước từ các video đã chạy</span>}>
          <div className="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(min(100%,460px),1fr))]">
            {making.map((r) => (
              <Making key={r.slug} row={r} />
            ))}
          </div>
        </Section>
      )}

      {queued.length > 0 && (
        <Section title="Đang xếp hàng" count={queued.length}>
          <Card className="gap-0 py-0">
            <ul className="divide-y divide-border">
              {queued.map((r) => (
                <Queued key={r.slug} row={r} canWrite={canWrite} refresh={refresh} />
              ))}
            </ul>
          </Card>
        </Section>
      )}

      {done.length > 0 && (
        <Section
          title="Video đã xong"
          count={done.length}
          aside={
            <Tabs
              label="Lọc video đã xong"
              value={filter}
              onChange={setFilter}
              options={[
                ['all', 'Tất cả'],
                ['fix', `Cần sửa (${toFix.length})`],
              ]}
            />
          }
        >
          {shown.length ? (
            <div className="grid gap-5 [grid-template-columns:repeat(auto-fill,minmax(min(100%,260px),1fr))]">
              {shown.map((r) => (
                <Finished key={r.slug} row={r} />
              ))}
            </div>
          ) : (
            <p className="text-muted-foreground">Không có video nào cần sửa.</p>
          )}
        </Section>
      )}

      {idle.length > 0 && (
        <details className="rounded-lg bg-card px-5 py-4">
          <summary className="cursor-pointer font-semibold">
            Chưa chạy tự động <span className="font-medium text-muted-foreground">· {idle.length} thư mục cũ, chạy tay trước khi có bảng điều khiển</span>
          </summary>
          <ul className="mt-3 flex flex-wrap gap-2">
            {idle.map((r) => (
              <li key={r.slug}>
                <a href={href(r)} className="inline-flex min-h-11 items-center rounded-lg bg-muted px-3 font-mono text-sm hover:bg-secondary">
                  {r.slug}
                </a>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}
