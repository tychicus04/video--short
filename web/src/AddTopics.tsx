// Paste topics, one per line; each gets a folder name (a guess Tai can edit) and goes into the queue together or not at all.
import { useState, type ReactNode } from 'react'
import { ListPlus, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { ApiError, errorMessage, post } from '@/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

const SLUG_RE = /^[a-z0-9][a-z0-9-]{0,59}$/ // as vshort/queue.py SLUG_RE
const MAX_TOPIC = 500

/** vshort/queue.py slugify, for a first guess only: the server checks the name it is given, not this one. */
export function slugify(topic: string): string {
  let t = topic.trim()
  if (/^https?:\/\//.test(t)) {
    try {
      const u = new URL(t)
      t = decodeURIComponent(u.pathname.replace(/\/+$/, '').split('/').pop() ?? '') || u.hostname
    } catch {
      /* keep the text as typed */
    }
  }
  t = t.toLowerCase().replace(/đ/g, 'd').normalize('NFKD').replace(/[̀-ͯ]/g, '')
  let s = t.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
  if (s.length > 60) {
    const head = s.slice(0, 60)
    const cut = head.lastIndexOf('-')
    s = s[60] === '-' || cut <= 0 ? head : head.slice(0, cut) // cut at a dash so the last word is whole
  }
  return s.replace(/^-+|-+$/g, '')
}

export function AddTopics({
  canWrite,
  maxRunning,
  refresh,
}: {
  canWrite: boolean
  maxRunning: number
  refresh: () => void
}) {
  const [text, setText] = useState('')
  const [edited, setEdited] = useState<Record<string, string>>({}) // topic -> the folder name Tai typed over the guess
  const [auto, setAuto] = useState(false)
  const [busy, setBusy] = useState(false)
  const [refused, setRefused] = useState<string[] | null>(null) // the server's message for each line

  const topics = text.split('\n').map((l) => l.trim()).filter(Boolean)
  const items = topics.map((topic) => ({ topic, slug: edited[topic] ?? slugify(topic) }))
  // only what the name itself shows; a name that is taken is for the server to say, under its line
  const local = items.map(({ topic, slug }) => {
    if (!slug) return 'Chủ đề không có chữ hay số nào để đặt tên thư mục'
    if (!SLUG_RE.test(slug)) return 'Tên thư mục chỉ gồm a-z, 0-9 và dấu -, tối đa 60 ký tự'
    if (topic.length > MAX_TOPIC) return `Chủ đề dài quá ${MAX_TOPIC} ký tự`
    return ''
  })
  const problem = (i: number) => refused?.[i] || local[i]

  const change = (fn: () => void) => {
    fn()
    setRefused(null)
  }

  async function submit() {
    setBusy(true)
    try {
      await post('/api/queue', { items, auto })
      toast.success(items.length === 1 ? `Đã thêm ${items[0].slug} vào hàng đợi` : `Đã thêm ${items.length} chủ đề vào hàng đợi`)
      setText('')
      setEdited({})
      setAuto(false) // "Bỏ duyệt brief" is for this batch only
      setRefused(null)
      refresh()
    } catch (e) {
      if (e instanceof ApiError && e.status === 400 && Array.isArray(e.data?.errors)) setRefused(e.data.errors)
      else toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-labelledby="new-h" className="flex flex-wrap gap-6 rounded-lg bg-card p-6">
      <div className="flex flex-[1_1_280px] flex-col gap-2">
        <h1 id="new-h" className="text-2xl leading-tight font-bold sm:text-[28px]">
          Tạo video ngắn từ một bài báo
        </h1>
        <p className="text-muted-foreground">
          Dán link bài báo hoặc gõ chủ đề, mỗi dòng một video. Chạy tối đa {maxRunning} video cùng lúc, phần còn lại xếp hàng.
        </p>
      </div>
      <div className="flex min-w-0 flex-[999_1_480px] flex-col gap-3">
        <label htmlFor="topics" className="text-sm text-muted-foreground">
          Link bài báo hoặc chủ đề
        </label>
        <Textarea
          id="topics"
          rows={3}
          value={text}
          onChange={(e) => change(() => setText(e.target.value))}
          placeholder={'Ví dụ:\nhttps://thehackernews.com/2026/11/...\nLỗ hổng nhân Linux CVE-2026-98432'}
          className="px-4 py-3"
        />

        {items.length > 0 && (
          <div className="overflow-hidden rounded-lg bg-muted">
            <Table className="table-fixed">
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="w-[46%] px-3 sm:w-72">Tên thư mục</TableHead>
                  <TableHead className="px-3">Chủ đề</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map(({ topic, slug }, i) => (
                  <RowPair key={i} topic={topic} slug={slug} message={problem(i)} onSlug={(v) => change(() => setEdited({ ...edited, [topic]: v }))} />
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
          <Switch id="auto-brief" checked={auto} onChange={setAuto}>
            <span className="font-semibold">Bỏ duyệt brief</span>
            <span className="text-sm text-muted-foreground"> · chạy thẳng tới bước duyệt bản dịch</span>
          </Switch>
          <div className="flex w-full items-center gap-3 sm:w-auto">
            {!canWrite && <span className="text-sm text-muted-foreground">Cần mã truy cập</span>}
            <Button size="lg" className="flex-1 sm:flex-none" onClick={submit} disabled={!canWrite || busy || !items.length || local.some(Boolean)}>
              {busy ? <Loader2 className="animate-spin" /> : <ListPlus />}
              Tạo video
              {items.length > 1 && ` (${items.length})`}
            </Button>
          </div>
        </div>
      </div>
    </section>
  )
}

/** An on/off switch: a real button with role="switch", the whole label is the target. */
function Switch({ id, checked, onChange, children }: { id: string; checked: boolean; onChange: (v: boolean) => void; children: ReactNode }) {
  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      <span aria-hidden className={cn('relative h-6 w-11 shrink-0 rounded-full transition-colors', checked ? 'bg-brand' : 'bg-secondary')}>
        <span className={cn('absolute top-0.5 left-0.5 size-5 rounded-full bg-foreground transition-transform', checked && 'translate-x-5')} />
      </span>
      <span>{children}</span>
    </button>
  )
}

function RowPair({ topic, slug, message, onSlug }: { topic: string; slug: string; message: string; onSlug: (v: string) => void }) {
  return (
    <>
      <TableRow className={message ? 'border-b-0' : undefined}>
        <TableCell className="px-3 align-top">
          <Input
            value={slug}
            onChange={(e) => onSlug(e.target.value)}
            spellCheck={false}
            autoCapitalize="none"
            aria-label={`Tên thư mục cho: ${topic}`}
            aria-invalid={message ? true : undefined}
            className="h-8 font-mono text-xs"
          />
        </TableCell>
        <TableCell className="px-3 pt-3 align-top whitespace-normal text-muted-foreground">
          <span className="line-clamp-3 break-words">{topic}</span>
        </TableCell>
      </TableRow>
      {message && (
        <TableRow className="hover:bg-transparent">
          <TableCell colSpan={2} className="px-3 pt-0 text-sm whitespace-normal text-destructive">
            {message}
          </TableCell>
        </TableRow>
      )}
    </>
  )
}
