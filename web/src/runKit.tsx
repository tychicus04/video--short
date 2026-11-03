// What the pages of one video share: the context RunDetail hands each of them, and the small pieces they all draw.
import { useEffect, useRef } from 'react'
import { TriangleAlert } from 'lucide-react'
import type { Detail } from '@/api'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

export interface Ctx {
  slug: string
  d: Detail
  canWrite: boolean
  /** a live `vshort auto` has the video: the server refuses every write */
  locked: boolean
  /** a write is out */
  busy: boolean
  /** writes are off: no access code, a live run, or another write still out */
  off: boolean
  /** run one write; `busy` is true meanwhile. Throws what `post` throws. */
  write: <T>(fn: () => Promise<T>) => Promise<T>
  /** read the video and the list again now */
  reload: () => Promise<void>
  hold: (unsaved: boolean) => void
}

export const runApi = (c: Ctx, tail: string) => `/api/runs/${encodeURIComponent(c.slug)}/${tail}`

/** Say whether this page has edits not saved yet: the 5-second refresh waits, and closing the tab asks first. */
export function useUnsaved(c: Ctx, unsaved: boolean) {
  const { hold } = c
  useEffect(() => {
    hold(unsaved)
    return () => hold(false)
  }, [hold, unsaved])
}

export interface Notice {
  kind: 'error' | 'warn'
  title?: string
  text: string
}

/** The answer to a write that did not go through, kept on the page until the next action. It scrolls itself into view: the button may be far from where it shows. */
export function NoticeBox({ n }: { n: Notice }) {
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    box.current?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [n])
  const warn = n.kind === 'warn'
  return (
    <div ref={box}>
      <Alert className={warn ? 'border-amber-500/30 bg-amber-500/10 text-amber-200' : 'border-red-500/30 bg-red-500/10 text-red-200'}>
        <TriangleAlert />
        {n.title && <AlertTitle>{n.title}</AlertTitle>}
        <AlertDescription className={cn('whitespace-pre-wrap [overflow-wrap:anywhere]', warn ? 'text-amber-100/85' : 'text-red-100/85')}>
          {n.text}
        </AlertDescription>
      </Alert>
    </div>
  )
}

/** Text as it was written: line breaks kept, a long path or link broken instead of pushing the page sideways. */
export function Message({ text, className }: { text: string; className?: string }) {
  return <div className={cn('text-sm whitespace-pre-wrap [overflow-wrap:anywhere]', className)}>{text}</div>
}

/** The last lines of auto.log in a box of their own. It sits at the newest line, and stays there while Tai is not reading further up. */
export function LogTail({ text }: { text: string }) {
  const box = useRef<HTMLPreElement>(null)
  const atEnd = useRef(true)
  useEffect(() => {
    const el = box.current
    if (el && atEnd.current) el.scrollTop = el.scrollHeight
  }, [text])
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Nhật ký</CardTitle>
        <CardDescription className="text-xs">Những dòng cuối của auto.log</CardDescription>
      </CardHeader>
      <div className="px-(--card-spacing)">
        <pre
          ref={box}
          tabIndex={0}
          onScroll={(e) => {
            const el = e.currentTarget
            atEnd.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24
          }}
          className="max-h-80 overflow-auto rounded-lg bg-black/30 p-3 font-mono text-xs leading-5 whitespace-pre text-muted-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
        >
          {text || '(nhật ký trống)'}
        </pre>
      </div>
    </Card>
  )
}
