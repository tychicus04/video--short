// What the pages of one video share: the context RunDetail hands each of them, and the small pieces they all draw.
import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react'
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

const kept = new Map<string, unknown>()

/**
 * useState for a draft that must outlive the page: leaving a video by a link, the logo or the back button unmounts it, and
 * coming back shows the draft again. Kept per video in memory only; reloading the tab drops it (beforeunload asks first).
 * The caller still drops a draft itself when it is saved, undone, or the file already says the same.
 */
export function useKept<T>(slug: string, name: string, initial: T): [T, Dispatch<SetStateAction<T>>] {
  const id = `${slug}/${name}`
  const [value, set] = useState<T>(() => (kept.has(id) ? (kept.get(id) as T) : initial))
  useEffect(() => {
    kept.set(id, value)
  }, [id, value])
  return [value, set]
}

export interface Notice {
  kind: 'error' | 'warn'
  title?: string
  text: string
}

/** The answer to a write that did not go through, kept on the page until the next action. It scrolls itself into view: the button may be far from where it shows.
 * `still`: a standing notice drawn from the 5-second refresh (a new object every time): never scrolls. */
export function NoticeBox({ n, still = false }: { n: Notice; still?: boolean }) {
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!still) box.current?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [n, still])
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

/** Puts text on the clipboard. The panel is plain http on the LAN, where navigator.clipboard does not exist: then the old way. */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    ta.remove()
    return ok
  }
}
