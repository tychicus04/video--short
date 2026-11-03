// Paste topics, one per line; each gets a folder name (a guess Tai can edit) and goes into the queue together or not at all.
import { useState } from 'react'
import { ListPlus, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { ApiError, errorMessage, post } from '@/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'

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
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ListPlus className="size-4 text-muted-foreground" /> Thêm chủ đề
        </CardTitle>
        <CardDescription>
          Mỗi dòng một chủ đề, hoặc một đường link bài báo. Máy chủ chạy tối đa {maxRunning} video cùng lúc, phần còn lại xếp hàng.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Textarea
          rows={4}
          value={text}
          onChange={(e) => change(() => setText(e.target.value))}
          placeholder={'Ví dụ:\nLỗ hổng nhân Linux CVE-2026-98432\nhttps://example.com/bai-viet-ve-chu-de-khac'}
          aria-label="Danh sách chủ đề, mỗi dòng một chủ đề"
        />

        {items.length > 0 && (
          <div className="overflow-hidden rounded-lg border">
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

        <label htmlFor="auto-brief" className="flex cursor-pointer items-start gap-2.5">
          <Checkbox id="auto-brief" checked={auto} onCheckedChange={(v) => setAuto(v === true)} className="mt-0.5" />
          <span className="text-sm">
            Bỏ duyệt brief
            <span className="block text-xs text-muted-foreground">Chạy thẳng, không dừng lại chờ bạn duyệt brief.</span>
          </span>
        </label>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <Button size="lg" onClick={submit} disabled={!canWrite || busy || !items.length || local.some(Boolean)}>
            {busy ? <Loader2 className="animate-spin" /> : <ListPlus />}
            Thêm vào hàng đợi
            {items.length > 1 && ` (${items.length})`}
          </Button>
          {!canWrite && <span className="text-sm text-muted-foreground">Cần mã truy cập</span>}
        </div>
      </CardContent>
    </Card>
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
