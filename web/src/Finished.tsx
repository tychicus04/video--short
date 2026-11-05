// A finished video (done): watch it, download it, read the final review and what it cost.
import { useState, type ComponentProps } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ChevronDown, Copy, Download, Film } from 'lucide-react'
import { toast } from 'sonner'
import type { CostEntry } from '@/api'
import { Message, copyText, type Ctx } from '@/runKit'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { fmtAgo, fmtDuration, money } from '@/status'

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
  a: (p) => <a className="text-sky-300 underline underline-offset-2 hover:text-sky-200" target="_blank" rel="noreferrer noopener" {...strip(p)} />,
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

/** What goes out with the video: the publish title, the headline covers, and the prompt for a poster cover drawn in the Gemini app. */
function Publish({ c }: { c: Ctx }) {
  const { slug, d } = c
  const title = d.row.title
  if (!title && d.cover_v == null && !d.prompt) return null
  const src = (shape: string) => `/files/${encodeURIComponent(slug)}/cover/thumb-${shape}.jpg?v=${d.cover_v}`
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Đăng bài</CardTitle>
        <CardDescription className="text-xs">Tiêu đề, ảnh bìa, và prompt để tự vẽ ảnh bìa trong app Gemini</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {title && (
          <div className="space-y-1.5">
            <div className="text-xs text-muted-foreground">Tiêu đề đăng</div>
            <div className="flex items-start gap-3">
              <p className="min-w-0 flex-1 text-sm font-medium [overflow-wrap:anywhere]">{title}</p>
              <Button size="sm" variant="outline" className="shrink-0" onClick={() => copy(title, 'tiêu đề')}>
                <Copy /> Sao chép
              </Button>
            </div>
          </div>
        )}

        {d.prompt ? (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-xs text-muted-foreground">1. Prompt ảnh bìa 9:16: dán vào app Gemini</div>
              <Button size="sm" className="shrink-0" onClick={() => copy(d.prompt!, 'prompt')}>
                <Copy /> Sao chép prompt
              </Button>
            </div>
            <pre className="max-h-56 overflow-y-auto rounded-lg bg-muted/40 p-3 text-xs leading-5 whitespace-pre-wrap [overflow-wrap:anywhere]">
              {d.prompt}
            </pre>
            <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
              <div className="text-xs text-muted-foreground">2. Có ảnh dọc rồi thì dán tiếp câu này, cùng cuộc trò chuyện, để có ảnh ngang 16:9 cho bài báo</div>
              <Button size="sm" variant="outline" className="shrink-0" onClick={() => copy(d.prompt_wide, 'câu 16:9')}>
                <Copy /> Sao chép câu 16:9
              </Button>
            </div>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">Video này chưa có prompt ảnh bìa: nó xong trước khi có bước viết prompt.</p>
        )}

        {d.cover_v != null && (
          <div className="space-y-1.5">
            <div className="text-xs text-muted-foreground">Ảnh bìa tự ghép từ ảnh bài báo (dự phòng), bấm để mở cỡ thật</div>
            <div className="flex items-end gap-3">
              <a href={src('9x16')} target="_blank" rel="noreferrer" className="shrink-0">
                <img src={src('9x16')} alt="Ảnh bìa dọc 9:16" className="h-36 rounded-md ring-1 ring-foreground/10" />
              </a>
              <a href={src('16x9')} target="_blank" rel="noreferrer" className="min-w-0">
                <img src={src('16x9')} alt="Ảnh bìa ngang 16:9" className="max-h-36 w-full max-w-64 rounded-md object-contain ring-1 ring-foreground/10" />
              </a>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function Finished({ c }: { c: Ctx }) {
  const { slug, d } = c
  const { row } = d
  const [reviewOpen, setReviewOpen] = useState(true)
  const file = `/files/${encodeURIComponent(slug)}/final.mp4`
  const ok = row.verdict === 'Đạt'

  return (
    <div className="grid gap-6 md:grid-cols-[17rem_minmax(0,1fr)] md:items-start">
      <div className="space-y-3 md:sticky md:top-20">
        <div className="relative mx-auto aspect-[9/16] w-full max-w-[22rem] overflow-hidden rounded-xl bg-black ring-1 ring-foreground/10">
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
            <Button asChild size="lg" className="h-10 w-full">
              <a href={`${file}?download=1`}>
                <Download /> Tải về
              </a>
            </Button>
          ) : (
            <Button size="lg" className="h-10 w-full" disabled>
              <Download /> Tải về
            </Button>
          )}
        </div>
      </div>

      <div className="min-w-0 space-y-4">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-muted-foreground">
          {row.verdict && (
            <Badge variant="outline" className={cn('h-6 px-2.5', ok ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300' : 'border-amber-500/30 bg-amber-500/10 text-amber-300')}>
              Soát: {row.verdict}
            </Badge>
          )}
          {row.seconds != null && <span>Dài {fmtDuration(row.seconds)}</span>}
          <span>Chi phí {money(row.cost)}</span>
          {row.since != null && <span>Xong {fmtAgo(row.since)}</span>}
        </div>

        <Publish c={c} />

        {row.message.trim() && (
          <Card size="sm">
            <CardHeader>
              <CardTitle>Ghi chú của lần chạy</CardTitle>
            </CardHeader>
            <CardContent>
              <Message text={row.message} className="text-muted-foreground" />
            </CardContent>
          </Card>
        )}

        {d.review_md && (
          <Card size="sm" className="gap-0 py-0">
            <button
              type="button"
              aria-expanded={reviewOpen}
              aria-controls="review-md"
              onClick={() => setReviewOpen(!reviewOpen)}
              className="flex w-full items-center gap-3 px-3 py-3 text-left outline-none hover:bg-accent/40 focus-visible:bg-accent/40"
            >
              <span className="flex-1 text-sm font-medium">Báo cáo soát (review.md)</span>
              <ChevronDown aria-hidden className={cn('size-4 shrink-0 text-muted-foreground transition-transform', reviewOpen && 'rotate-180')} />
            </button>
            {reviewOpen && (
              <div id="review-md" className="border-t px-4 py-4 break-words">
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>
                  {d.review_md}
                </ReactMarkdown>
              </div>
            )}
          </Card>
        )}

        {d.cost.length > 0 && <CostTable cost={d.cost} />}
      </div>
    </div>
  )
}
