// A finished video (done): watch it, download it, and in tabs: what to post (title, covers, Gemini covers to upload), the
// final review, the ten stages and what it cost.
import { useState, type ComponentProps } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Copy, Download, Film, ImageUp, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { ApiError, post, type CostEntry } from '@/api'
import { Message, copyText, runApi, useKept, type Ctx } from '@/runKit'
import { StageList } from '@/Stages'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { Tabs, fmtAgo, fmtDuration, money } from '@/status'

/** review.md, drawn with our own styles: no HTML in it is rendered (react-markdown leaves it as text) and links are made safe by the library. */
const MD: ComponentProps<typeof ReactMarkdown>['components'] = {
  h1: (p) => <h2 className="mt-1 mb-3 text-lg font-semibold tracking-tight" {...strip(p)} />,
  h2: (p) => <h3 className="mt-7 mb-2 border-b pb-1.5 text-base font-semibold" {...strip(p)} />,
  h3: (p) => <h4 className="mt-5 mb-1.5 text-sm font-semibold" {...strip(p)} />,
  h4: (p) => <h5 className="mt-4 mb-1 text-sm font-medium" {...strip(p)} />,
  p: (p) => <p className="my-2.5 text-sm leading-6 text-foreground/90" {...strip(p)} />,
  ul: (p) => <ul className="my-2.5 list-disc space-y-1 pl-5 text-sm leading-6 text-foreground/90" {...strip(p)} />,
  ol: (p) => <ol className="my-2.5 list-decimal space-y-1 pl-5 text-sm leading-6 text-foreground/90" {...strip(p)} />,
  strong: (p) => <strong className="font-semibold text-foreground" {...strip(p)} />,
  a: (p) => <a className="text-brand-text underline underline-offset-2 hover:text-foreground" target="_blank" rel="noreferrer noopener" {...strip(p)} />,
  blockquote: (p) => <blockquote className="my-3 border-l-2 pl-3 text-muted-foreground" {...strip(p)} />,
  hr: () => <hr className="my-5" />,
  code: (p) => <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em] break-words" {...strip(p)} />,
  pre: (p) => <pre className="my-3 overflow-x-auto rounded-lg bg-black/30 p-3 text-xs leading-5 [&_code]:bg-transparent [&_code]:p-0" {...strip(p)} />,
  // a table can be wider than a phone: it scrolls inside its own box instead of widening the page
  table: (p) => (
    <div className="my-3 overflow-x-auto rounded-lg border">
      <table className="w-full min-w-[40rem] border-collapse text-xs leading-5" {...strip(p)} />
    </div>
  ),
  th: (p) => <th className="border-b bg-muted/40 px-2.5 py-1.5 text-left align-top font-medium whitespace-nowrap" {...strip(p)} />,
  td: (p) => <td className="border-b px-2.5 py-1.5 align-top" {...strip(p)} />,
  img: ({ alt }) => <span className="text-muted-foreground">[{alt || 'hình'}]</span>, // the pictures of the review stay on the server
}

/** react-markdown passes its syntax node along; it is not an attribute. */
function strip<T extends { node?: unknown }>(p: T): Omit<T, 'node'> {
  const { node: _node, ...rest } = p
  return rest
}

const usd = (x: number) => `$${x.toFixed(3)}`

function CostTable({ cost }: { cost: CostEntry[] }) {
  return (
    <Card size="sm" className="gap-0 pb-0">
      <CardHeader className="pb-3">
        <CardTitle>Chi phí Claude</CardTitle>
        <CardDescription className="text-xs">Từng bước chạy bằng agent</CardDescription>
      </CardHeader>
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="px-3">Bước</TableHead>
            <TableHead className="px-3 max-sm:hidden">Agent</TableHead>
            <TableHead className="px-3 text-right">Giây</TableHead>
            <TableHead className="px-3 text-right">Chi phí</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {cost.map((e, i) => (
            <TableRow key={i} className={cn('hover:bg-transparent', !e.ok && 'bg-red-500/[0.06]')}>
              <TableCell className="px-3 font-mono text-xs">
                {e.step}
                {!e.ok && <span className="ml-1.5 font-sans text-red-300">lỗi</span>}
                <div className="font-sans text-muted-foreground sm:hidden">{e.agent}</div>
              </TableCell>
              <TableCell className="px-3 text-xs text-muted-foreground max-sm:hidden" title={e.models.join(', ')}>
                {e.agent}
              </TableCell>
              <TableCell className="px-3 text-right text-xs tabular-nums">{Math.round(e.seconds)}</TableCell>
              <TableCell className="px-3 text-right text-xs tabular-nums">{usd(e.cost_usd)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
        <TableFooter>
          <TableRow className="hover:bg-transparent">
            <TableCell className="px-3">Tổng</TableCell>
            <TableCell className="max-sm:hidden" />
            <TableCell className="px-3 text-right text-xs tabular-nums">{Math.round(cost.reduce((s, e) => s + e.seconds, 0))}</TableCell>
            <TableCell className="px-3 text-right tabular-nums">{money(cost.reduce((s, e) => s + e.cost_usd, 0))}</TableCell>
          </TableRow>
        </TableFooter>
      </Table>
    </Card>
  )
}

async function copy(text: string, what: string) {
  if (await copyText(text)) toast.success(`Đã sao chép ${what}`)
  else toast.error(`Không sao chép được ${what}, hãy bôi đen rồi chép tay`)
}

type Shape = '9x16' | '16x9'
const SHAPE: Record<Shape, { label: string; box: string }> = {
  '9x16': { label: '9:16 (dọc)', box: 'aspect-[9/16] w-[180px]' },
  '16x9': { label: '16:9 (ngang)', box: 'aspect-video w-[300px] max-w-full' },
}

/** A file as base64, without the "data:image/png;base64," in front: what POST /api/runs/<slug>/cover takes. */
const base64 = (file: File) =>
  new Promise<string>((ok, bad) => {
    const r = new FileReader()
    r.onload = () => ok(String(r.result).replace(/^data:[^,]*,/, ''))
    r.onerror = () => bad(r.error)
    r.readAsDataURL(file)
  })

/** One Gemini cover: drop a picture on it or tap to choose one; once there, it shows, and "Thay ảnh" picks another. */
function GeminiDrop({ c, shape }: { c: Ctx; shape: Shape }) {
  const v = c.d.gemini[shape]
  const { label, box } = SHAPE[shape]
  const id = `gemini-${shape}`
  const [over, setOver] = useState(false)
  const [sending, setSending] = useState(false)

  async function send(file: File | undefined) {
    if (!file || c.off) return
    if (file.size > 15_000_000) return void toast.error('Ảnh lớn quá 15 MB')
    setSending(true)
    try {
      const data = await base64(file)
      await c.write(() => post(runApi(c, 'cover'), { shape, data }))
      toast.success(`Đã lưu ảnh Gemini ${label}`)
      await c.reload()
    } catch (e) {
      toast.error(e instanceof ApiError ? e.error : 'Không đọc được file ảnh này')
    } finally {
      setSending(false)
    }
  }

  return (
    <figure className="flex w-min flex-col gap-2">
      <label
        htmlFor={id}
        onDragOver={(e) => {
          e.preventDefault()
          setOver(true)
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setOver(false)
          send(e.dataTransfer.files[0])
        }}
        className={cn(
          'relative grid place-items-center overflow-hidden rounded-lg bg-muted p-3 text-center text-sm text-muted-foreground has-focus-visible:ring-3 has-focus-visible:ring-ring/50',
          box,
          over && 'ring-2 ring-brand',
          c.off ? 'cursor-not-allowed' : 'cursor-pointer hover:bg-secondary',
        )}
      >
        <input id={id} type="file" accept="image/*" className="sr-only" disabled={c.off} onChange={(e) => {
            send(e.target.files?.[0])
            e.target.value = '' // the same file chosen again must fire onChange again
          }}
        />
        {v != null ? (
          <img src={`/files/${encodeURIComponent(c.slug)}/cover/gemini-${shape}.jpg?v=${v}`} alt={`Ảnh bìa Gemini ${label}`} className="absolute inset-0 size-full object-cover" />
        ) : (
          <span className="flex flex-col items-center gap-2">
            {sending ? <Loader2 className="size-6 animate-spin" /> : <ImageUp className="size-6" />}
            {sending ? 'Đang gửi…' : `Kéo ảnh ${label} vào đây, hoặc bấm để chọn`}
          </span>
        )}
      </label>
      <figcaption className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span>
          <span className="font-semibold">Ảnh Gemini {label}</span>
          {v != null && <span className="text-muted-foreground"> · dùng khi đăng</span>}
        </span>
        {v != null && (
          <label htmlFor={id} className={cn(buttonVariants({ variant: 'outline', size: 'sm' }), c.off ? 'pointer-events-none opacity-50' : 'cursor-pointer')}>
            {sending ? <Loader2 className="animate-spin" /> : <ImageUp />} Thay ảnh
          </label>
        )}
      </figcaption>
    </figure>
  )
}

/** The tab "Đăng bài": the publish title, the covers (Tai's Gemini ones, the composed ones as a fallback), how to draw them. */
function Publish({ c }: { c: Ctx }) {
  const { slug, d } = c
  const title = d.row.title
  const src = (shape: string) => `/files/${encodeURIComponent(slug)}/cover/thumb-${shape}.jpg?v=${d.cover_v}`
  return (
    <div className="space-y-4">
      <section aria-labelledby="t-h" className="space-y-2 rounded-lg bg-card p-5">
        <h2 id="t-h" className="text-sm font-medium text-muted-foreground">
          Tiêu đề đăng
        </h2>
        {title ? (
          <div className="flex flex-wrap items-center gap-3">
            <p className="min-w-0 flex-[1_1_320px] text-[17px] font-semibold [overflow-wrap:anywhere]">{title}</p>
            <Button size="sm" variant="outline" className="shrink-0" onClick={() => copy(title, 'tiêu đề')}>
              <Copy /> Sao chép
            </Button>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Chưa có tiêu đề đăng: video này xong trước khi có bước viết tiêu đề.</p>
        )}
      </section>

      <section aria-labelledby="c-h" className="space-y-4 rounded-lg bg-card p-5">
        <h2 id="c-h" className="text-lg font-semibold">
          Ảnh bìa
        </h2>
        <div className="flex flex-wrap items-start gap-5">
          <GeminiDrop c={c} shape="9x16" />
          <GeminiDrop c={c} shape="16x9" />
          {d.cover_v != null && (
            <figure className="flex flex-col gap-2">
              <a href={src('9x16')} target="_blank" rel="noreferrer" className="flex gap-2">
                <img src={src('9x16')} alt="Ảnh bìa tự ghép dọc 9:16" className="h-32 rounded-lg opacity-85" />
                <img src={src('16x9')} alt="Ảnh bìa tự ghép ngang 16:9" className="h-[72px] rounded-lg opacity-85" />
              </a>
              <figcaption className="text-sm text-muted-foreground">Ảnh tự ghép · dự phòng khi chưa có ảnh Gemini</figcaption>
            </figure>
          )}
        </div>
        {!c.canWrite && <p className="text-sm text-muted-foreground">Cần mã truy cập để tải ảnh lên.</p>}

        <div className="space-y-3 rounded-lg bg-muted p-4">
          <div className="font-semibold">Vẽ ảnh bìa trong app Gemini</div>
          {d.prompt ? (
            <>
              <ol className="list-decimal space-y-1.5 pl-5 text-sm">
                <li>Sao chép prompt, dán vào Gemini, được ảnh dọc 9:16.</li>
                <li>Dán tiếp câu 16:9 vào cùng cuộc trò chuyện, được ảnh ngang cho bài báo.</li>
                <li>Kéo cả hai ảnh vào hai ô ở trên.</li>
              </ol>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => copy(d.prompt!, 'prompt')}>
                  <Copy /> Sao chép prompt
                </Button>
                <Button variant="outline" onClick={() => copy(d.prompt_wide, 'câu 16:9')}>
                  <Copy /> Sao chép câu 16:9
                </Button>
              </div>
              <details>
                <summary className="cursor-pointer text-sm text-muted-foreground">Xem prompt</summary>
                <pre className="mt-2 max-h-56 overflow-y-auto rounded-lg bg-card p-3 text-xs leading-5 whitespace-pre-wrap [overflow-wrap:anywhere]">{d.prompt}</pre>
              </details>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Video này chưa có prompt ảnh bìa: nó xong trước khi có bước viết prompt.</p>
          )}
        </div>
      </section>
    </div>
  )
}

type Tab = 'post' | 'review' | 'steps' | 'cost'

export function Finished({ c }: { c: Ctx }) {
  const { slug, d } = c
  const { row } = d
  const [tab, setTab] = useKept<Tab>(slug, 'tab', 'post')
  const file = `/files/${encodeURIComponent(slug)}/final.mp4`
  const ok = row.verdict === 'Đạt'

  return (
    <div className="grid gap-7 md:grid-cols-[20rem_minmax(0,1fr)] md:items-start">
      <div className="space-y-3 md:sticky md:top-24">
        <div className="relative mx-auto aspect-[9/16] w-full max-w-[22rem] overflow-hidden rounded-lg bg-black">
          {d.video ? (
            // #t=0.1: show a frame instead of black before play. The address stays the same, so a refresh never restarts it.
            <video className="absolute inset-0 size-full object-contain" controls playsInline preload="metadata" src={`${file}#t=0.1`} />
          ) : (
            <div className="absolute inset-0 grid place-items-center p-6 text-center text-sm text-muted-foreground">
              <div className="space-y-2">
                <Film className="mx-auto size-6" />
                <p>Chưa xem được: video chưa có file hoặc đang được dựng lại.</p>
              </div>
            </div>
          )}
        </div>
        <div className="mx-auto max-w-[22rem]">
          {d.video ? (
            <Button asChild size="lg" variant="outline" className="w-full">
              <a href={`${file}?download=1`}>
                <Download /> Tải video
              </a>
            </Button>
          ) : (
            <Button size="lg" variant="outline" className="w-full" disabled>
              <Download /> Tải video
            </Button>
          )}
        </div>
      </div>

      <div className="min-w-0 space-y-5">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-muted-foreground">
          {row.verdict && (
            <span className={cn('rounded-full px-3 py-1 text-[13px] font-semibold', ok ? 'bg-ok/15 text-ok' : 'bg-wait-bg text-wait')}>Soát: {row.verdict}</span>
          )}
          {row.seconds != null && <span>Dài {fmtDuration(row.seconds)}</span>}
          <span>Chi phí {money(row.cost)}</span>
          {row.since != null && <span>Xong {fmtAgo(row.since)}</span>}
        </div>

        <Tabs
          label="Phần của video"
          value={tab}
          onChange={setTab}
          className="max-w-xl"
          options={[
            ['post', 'Đăng bài'],
            ['review', 'Báo cáo soát'],
            ['steps', 'Các bước'],
            ['cost', 'Chi phí'],
          ]}
        />

        <div role="tabpanel" aria-label={{ post: 'Đăng bài', review: 'Báo cáo soát', steps: 'Các bước', cost: 'Chi phí' }[tab]}>
          {tab === 'post' && <Publish c={c} />}
          {tab === 'review' && (
            <div className="space-y-4">
              {d.review_md ? (
                <div className="rounded-lg bg-card px-5 py-4 break-words">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>
                    {d.review_md}
                  </ReactMarkdown>
                </div>
              ) : (
                <p className="text-muted-foreground">Video này không có báo cáo soát (review.md).</p>
              )}
              {row.message.trim() && (
                <section aria-labelledby="note-h" className="space-y-2 rounded-lg bg-card p-5">
                  <h2 id="note-h" className="font-semibold">
                    Ghi chú của lần chạy
                  </h2>
                  <Message text={row.message} className="text-muted-foreground" />
                </section>
              )}
            </div>
          )}
          {tab === 'steps' && (
            <section className="rounded-lg bg-card p-6">
              <StageList view={d.progress} auto={row.auto} />
            </section>
          )}
          {tab === 'cost' && (d.cost.length > 0 ? <CostTable cost={d.cost} /> : <p className="text-muted-foreground">Chưa ghi chi phí nào.</p>)}
        </div>
      </div>
    </div>
  )
}
