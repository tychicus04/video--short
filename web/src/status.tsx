// What each state of a video looks like (label, colour, icon), and the small formatters the list and the detail page share.
import {
  CircleCheck,
  CircleDashed,
  ClipboardCheck,
  Clock,
  Loader2,
  TriangleAlert,
  Unplug,
  type LucideIcon,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { RowState } from '@/api'

interface Meta {
  label: string
  icon: LucideIcon
  badge: string // colour of the Badge
  bar?: string // left edge of a row that needs Tai
  tint?: string // background of that row
  spin?: boolean
}

export const STATE: Record<RowState, Meta> = {
  queued: { label: 'Đang xếp hàng', icon: Clock, badge: 'bg-zinc-500/15 text-zinc-300 border-zinc-500/25' },
  running: { label: 'Đang chạy', icon: Loader2, spin: true, badge: 'bg-sky-500/15 text-sky-300 border-sky-500/25' },
  dead: {
    label: 'Dừng giữa chừng',
    icon: Unplug,
    badge: 'bg-orange-500/15 text-orange-300 border-orange-500/30',
    bar: 'bg-orange-400',
    tint: 'bg-orange-500/[0.05]',
  },
  wait_brief: {
    label: 'Chờ duyệt brief',
    icon: ClipboardCheck,
    badge: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
    bar: 'bg-amber-400',
    tint: 'bg-amber-500/[0.06]',
  },
  wait_script: {
    label: 'Chờ duyệt bản dịch',
    icon: ClipboardCheck,
    badge: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
    bar: 'bg-amber-400',
    tint: 'bg-amber-500/[0.06]',
  },
  error: {
    label: 'Lỗi',
    icon: TriangleAlert,
    badge: 'bg-red-500/15 text-red-300 border-red-500/30',
    bar: 'bg-red-400',
    tint: 'bg-red-500/[0.06]',
  },
  done: { label: 'Xong', icon: CircleCheck, badge: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25' },
  idle: { label: 'Chưa chạy tự động', icon: CircleDashed, badge: 'bg-transparent text-muted-foreground border-border' },
}

export function StatusBadge({ state, className }: { state: RowState; className?: string }) {
  const m = STATE[state]
  return (
    <Badge variant="outline" className={cn('h-6 gap-1.5 px-2.5', m.badge, className)}>
      <m.icon className={m.spin ? 'animate-spin' : undefined} />
      {m.label}
    </Badge>
  )
}

/** A length of time in seconds: "45 giây", "1 phút 02 giây", "2 giờ 05 phút". */
export function fmtDuration(s: number): string {
  s = Math.max(0, Math.round(s))
  if (s < 60) return `${s} giây`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} phút ${String(s % 60).padStart(2, '0')} giây`
  return `${Math.floor(m / 60)} giờ ${String(m % 60).padStart(2, '0')} phút`
}

/** Time left, coarse: "khoảng 21 phút", "khoảng 1 giờ 5 phút", "dưới 1 phút", "—" when unknown. */
export function fmtLeft(seconds: number | null): string {
  if (seconds == null) return '—'
  if (seconds < 60) return 'dưới 1 phút'
  const m = Math.round(seconds / 60)
  return m < 60 ? `khoảng ${m} phút` : `khoảng ${Math.floor(m / 60)} giờ${m % 60 ? ` ${m % 60} phút` : ''}`
}

/** When something `seconds` from now happens, on the viewer's clock: "~14:33". The server's `now` is not needed: the
 * seconds count from the moment the page was read, a few seconds ago at most. */
export function fmtClock(seconds: number): string {
  return '~' + new Date(Date.now() + seconds * 1000).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })
}

/** How long ago an epoch-seconds time was, coarse: "vừa xong", "5 phút trước", "3 giờ trước", "2 ngày trước". */
export function fmtAgo(since: number | null): string {
  if (since == null) return ''
  const s = Date.now() / 1000 - since
  if (s < 45) return 'vừa xong'
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))} phút trước`
  if (s < 86400) return `${Math.round(s / 3600)} giờ trước`
  return `${Math.round(s / 86400)} ngày trước`
}

export const money = (usd: number) => `$${usd.toFixed(2)}`

export const firstLine = (text: string) => text.split('\n').find((l) => l.trim())?.trim() ?? ''

/** A video's length as on a player: "1:03". */
export function fmtClockLength(s: number): string {
  const t = Math.round(s)
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`
}

/** Clipcup's tabs: a dark track, the chosen one white with dark text. Wraps on a phone. */
export function Tabs<T extends string>({
  value,
  options,
  onChange,
  label,
  className,
}: {
  value: T
  options: [T, string][]
  onChange: (v: T) => void
  label: string
  className?: string
}) {
  return (
    <div role="tablist" aria-label={label} className={cn('flex flex-wrap gap-1 rounded-xl bg-card p-1', className)}>
      {options.map(([v, text]) => (
        <button
          key={v}
          type="button"
          role="tab"
          aria-selected={v === value}
          onClick={() => onChange(v)}
          className={cn(
            'min-h-[42px] flex-1 rounded-lg px-4 text-sm whitespace-nowrap outline-none focus-visible:ring-3 focus-visible:ring-ring/50',
            v === value
              ? 'bg-foreground font-bold text-card shadow-[-20px_10px_30px_rgba(0,0,0,0.25)]'
              : 'font-semibold text-foreground hover:bg-secondary',
          )}
        >
          {text}
        </button>
      ))}
    </div>
  )
}
