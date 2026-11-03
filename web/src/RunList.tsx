// The list of every video, grouped by what Tai has to do about it. The server already sorts the rows in that order.
import { useState } from 'react'
import { ChevronRight, X } from 'lucide-react'
import { toast } from 'sonner'
import { errorMessage, post, type Row, type RowState } from '@/api'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { STATE, StatusBadge, firstLine, fmtAgo, fmtDuration, money } from '@/status'

const GROUPS: { title: string; states: RowState[]; tone?: string }[] = [
  { title: 'Cần bạn xử lý', states: ['wait_brief', 'wait_script', 'error', 'dead'], tone: 'text-amber-300' },
  { title: 'Đang chạy và xếp hàng', states: ['running', 'queued'] },
  { title: 'Đã xong', states: ['done'] },
  { title: 'Chưa chạy tự động', states: ['idle'] },
]

function Facts({ row }: { row: Row }) {
  const dot = <span aria-hidden>·</span>
  switch (row.state) {
    case 'running':
      return (
        <>
          <span className="font-medium text-sky-300">{row.step ?? 'Đang chạy'}</span>
          {row.since != null && (
            <>
              {dot}
              <span>{fmtDuration(Date.now() / 1000 - row.since)}</span>
            </>
          )}
        </>
      )
    case 'queued':
      return (
        <>
          <span>Chờ tới lượt</span>
          {row.since != null && (
            <>
              {dot}
              <span>thêm {fmtAgo(row.since)}</span>
            </>
          )}
          {row.auto && (
            <>
              {dot}
              <span>bỏ duyệt brief</span>
            </>
          )}
        </>
      )
    case 'error':
    case 'dead':
      return (
        <span className={cn('line-clamp-2 break-words', row.state === 'error' ? 'text-red-300/90' : 'text-orange-300/90')}>
          {firstLine(row.message) || 'Không có lời nhắn, mở ra xem nhật ký'}
        </span>
      )
    case 'wait_brief':
    case 'wait_script':
      return <span className="text-amber-200/90">Bấm vào để xem và duyệt</span>
    case 'done':
      return (
        <>
          {row.verdict && (
            <>
              <span className={row.verdict === 'Đạt' ? 'font-medium text-emerald-300' : 'font-medium text-amber-300'}>
                Soát: {row.verdict}
              </span>
              {dot}
            </>
          )}
          <span>{money(row.cost)}</span>
          {row.seconds != null && (
            <>
              {dot}
              <span>{fmtDuration(row.seconds)}</span>
            </>
          )}
        </>
      )
    default:
      return <span>Chưa có lần chạy nào</span>
  }
}

function Item({ row, canWrite, refresh }: { row: Row; canWrite: boolean; refresh: () => void }) {
  const [busy, setBusy] = useState(false)
  const m = STATE[row.state]

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
    <li className={cn('relative px-4 py-3 transition-colors hover:bg-accent/40', m.tint)}>
      {m.bar && <span aria-hidden className={cn('absolute inset-y-0 left-0 w-1', m.bar)} />}
      <div className="flex items-center gap-3">
        <a
          href={`#/r/${encodeURIComponent(row.slug)}`}
          className="min-w-0 flex-1 truncate font-mono text-sm font-medium outline-none after:absolute after:inset-0 focus-visible:after:ring-2 focus-visible:after:ring-ring/60 focus-visible:after:ring-inset"
        >
          {row.slug}
        </a>
        <StatusBadge state={row.state} className="shrink-0" />
        <ChevronRight aria-hidden className="hidden size-4 shrink-0 text-muted-foreground sm:block" />
      </div>
      <p className="mt-1 line-clamp-2 text-sm break-words text-muted-foreground">
        {row.topic || <span className="italic">(chưa có chủ đề)</span>}
      </p>
      <div className="mt-1.5 flex min-h-6 items-center justify-between gap-3 text-xs text-muted-foreground">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5">
          <Facts row={row} />
        </div>
        {row.removable && (
          <Button
            variant="outline"
            size="xs"
            className="relative z-10 shrink-0"
            disabled={!canWrite || busy}
            title={canWrite ? 'Gỡ chủ đề này khỏi hàng đợi' : 'Cần mã truy cập'}
            onClick={remove}
          >
            <X /> Gỡ
          </Button>
        )}
      </div>
    </li>
  )
}

export function RunList({ rows, canWrite, refresh }: { rows: Row[] | null; canWrite: boolean; refresh: () => void }) {
  if (rows === null)
    return (
      <Card className="gap-0 py-0" aria-busy="true" aria-label="Đang tải danh sách">
        {[0, 1, 2].map((i) => (
          <div key={i} className="space-y-2 border-b px-4 py-3 last:border-0">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-4 w-4/5" />
            <Skeleton className="h-3 w-1/4" />
          </div>
        ))}
      </Card>
    )

  if (rows.length === 0)
    return (
      <Card className="py-10 text-center text-muted-foreground">
        Chưa có video nào. Thêm chủ đề ở ô phía trên để bắt đầu.
      </Card>
    )

  return (
    <div className="space-y-6">
      {GROUPS.map((g) => {
        const part = rows.filter((r) => g.states.includes(r.state))
        if (!part.length) return null
        return (
          <section key={g.title}>
            <h2 className={cn('mb-2 flex items-center gap-2 text-sm font-medium', g.tone ?? 'text-muted-foreground')}>
              {g.title}
              <span className="rounded-full bg-muted px-2 py-px text-xs font-normal text-muted-foreground">{part.length}</span>
            </h2>
            <Card className="gap-0 py-0">
              <ul className="divide-y divide-border">
                {part.map((r) => (
                  <Item key={r.slug} row={r} canWrite={canWrite} refresh={refresh} />
                ))}
              </ul>
            </Card>
          </section>
        )
      })}
    </div>
  )
}
