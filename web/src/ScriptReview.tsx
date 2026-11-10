// A video waiting for its translation to be approved (wait_script): each English sentence next to its Vietnamese phrases.
// A "|" in the Vietnamese marks where the subtitle breaks into chunks. Tai edits the text and the bars come back to the server as typed.
import { useEffect, useState } from 'react'
import { Check, CircleCheck, Loader2, Save, TriangleAlert, Undo2 } from 'lucide-react'
import { toast } from 'sonner'
import { errorMessage, post, type ProposedRow, type TranslationRow } from '@/api'
import { NoticeBox, runApi, useKept, useUnsaved, type Ctx, type Notice } from '@/runKit'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

/** One line of Vietnamese. A plain textarea, so every "|" is plain text exactly as typed. Telex/IME and iOS autocorrect must not touch it. */
function PhraseField({
  id,
  value,
  onChange,
  readOnly,
  invalid,
}: {
  id: number
  value: string
  onChange: (v: string) => void
  readOnly: boolean
  invalid: boolean
}) {
  return (
    <Textarea
      aria-label={`Lời Việt của câu ${id}`}
      aria-invalid={invalid || undefined}
      rows={Math.max(1, Math.ceil(value.length / 34))} // for a browser without field-sizing: about one row per 34 characters
      value={value}
      readOnly={readOnly}
      spellCheck={false}
      autoCorrect="off"
      autoCapitalize="off"
      enterKeyHint="done"
      onChange={(e) => onChange(e.target.value.replace(/\r?\n/g, ' '))} // a subtitle is one line; only pasted line breaks get here
      onKeyDown={(e) => {
        if (e.key === 'Enter' && !e.nativeEvent.isComposing) e.preventDefault() // not while a Telex word is still being composed
      }}
      className={cn('min-h-0 resize-none px-2.5 py-1.5 leading-6', readOnly && 'opacity-70')}
    />
  )
}

function Proposal({ now, p }: { now: TranslationRow; p: ProposedRow | undefined }) {
  if (!p) return <span className="text-muted-foreground">—</span>
  if (p.phrases === now.phrases && p.note === now.note) return <span className="text-xs text-muted-foreground">Giống bản hiện tại</span>
  return (
    <div className="rounded-lg border border-emerald-500/25 bg-emerald-500/[0.07] px-2.5 py-1.5 text-sm leading-6 break-words whitespace-pre-wrap">
      {p.phrases}
      {p.note !== now.note && <div className="mt-1 text-xs text-muted-foreground">Ghi chú: {p.note || '(bỏ ghi chú)'}</div>}
    </div>
  )
}

/** The labels a cell shows above its content when the table is stacked into cards on a phone. */
const CELL = 'whitespace-normal align-top max-md:block max-md:px-0 max-md:py-1 md:px-2 md:py-3'
const LABEL = 'max-md:before:mb-1 max-md:before:block max-md:before:text-xs max-md:before:text-muted-foreground max-md:before:content-[attr(data-label)]'

export function ScriptReview({ c }: { c: Ctx }) {
  const { d } = c
  const rows = d.translation
  const proposed = d.proposed
  // id -> the Vietnamese Tai typed, only where it differs from the file. Kept when Tai leaves this video and comes back.
  const [drafts, setDrafts] = useKept<Record<number, string>>(c.slug, 'script.rows', {})
  const [result, setResult] = useState<{ ok: boolean; problems: string[] } | null>(null)
  const [notice, setNotice] = useState<Notice | null>(null)
  const [doing, setDoing] = useState<'save' | 'approve' | 'proposal' | null>(null)

  const dirty = Object.keys(drafts).length > 0
  useUnsaved(c, dirty)

  // the file changed under the drafts (the save went through, or the proposal replaced it): a draft that says what the file says is gone
  useEffect(() => {
    if (!rows) return
    setDrafts((prev) => {
      // gone: the file says the same, or the sentence is no longer in the translation
      const keep = Object.entries(prev).filter(([id, text]) => {
        const row = rows.find((r) => r.id === Number(id))
        return row && row.phrases !== text
      })
      return keep.length === Object.keys(prev).length ? prev : Object.fromEntries(keep)
    })
  }, [rows, setDrafts])

  if (!rows)
    return (
      <Alert className="border-amber-500/30 bg-amber-500/10 text-amber-200">
        <TriangleAlert />
        <AlertTitle>Chưa đọc được bản dịch</AlertTitle>
        <AlertDescription className="text-amber-100/80">Thiếu file bản dịch hoặc file bị hỏng. Xem nhật ký của video hoặc chạy lại bước dịch.</AlertDescription>
      </Alert>
    )

  const edit = (r: TranslationRow, text: string) =>
    setDrafts((p) => {
      const { [r.id]: _old, ...rest } = p
      return text === r.phrases ? rest : { ...rest, [r.id]: text }
    })

  /** `go` is one write; its failure becomes the notice. Afterwards the page reads the video again. */
  async function act(what: 'save' | 'approve' | 'proposal', go: () => Promise<void>) {
    setNotice(null)
    setDoing(what)
    try {
      await go()
    } catch (e) {
      setNotice({ kind: 'error', text: errorMessage(e) }) // approve: the CLI's own message, several lines
    } finally {
      setDoing(null)
      await c.reload()
    }
  }

  const save = () =>
    act('save', async () => {
      // every row, as it is in the file unless Tai changed it: nothing trimmed, nothing re-split
      const r = await c.write(() => post(runApi(c, 'script'), { rows: rows.map((x) => ({ id: x.id, phrases: drafts[x.id] ?? x.phrases, note: x.note })) }))
      setResult({ ok: !!r?.ok, problems: Array.isArray(r?.problems) ? r.problems : [] })
      if (r?.ok) toast.success('Đã lưu, kịch bản hợp lệ')
      else toast.warning('Đã lưu, còn chỗ cần sửa')
    })

  const approve = () =>
    act('approve', async () => {
      await c.write(() => post(runApi(c, 'approve'), { what: 'script' }))
      toast.success('Đã duyệt bản dịch, video quay lại hàng đợi')
    })

  const answer = (use: boolean) =>
    act('proposal', async () => {
      await c.write(() => post(runApi(c, 'proposal'), { use }))
      setResult(null)
      toast.success(use ? 'Đã dùng bản đề xuất' : 'Đã bỏ bản đề xuất')
    })

  const prop = new Map((proposed ?? []).map((p) => [p.id, p]))
  const changes = (r: TranslationRow) => {
    const p = prop.get(r.id)
    return !!p && (p.phrases !== r.phrases || p.note !== r.note)
  }
  const differing = rows.filter(changes).length
  // "Câu 5: …" in a problem: that row is marked until Tai types in it again
  const flagged = new Set((result?.problems ?? []).flatMap((p) => { const m = /câu (\d+)/i.exec(p); return m ? [Number(m[1])] : [] }))

  const why = !c.canWrite ? 'Cần mã truy cập' : dirty ? 'Có chỗ sửa chưa lưu: bấm “Lưu và kiểm” trước khi duyệt' : proposed ? 'Còn bản đề xuất chưa trả lời' : ''

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Đối chiếu từng câu, sửa lời Việt ngay trong ô. Dấu <span className="font-mono text-foreground">|</span> là chỗ ngắt cụm phụ đề, giữ nguyên khi sửa.
      </p>

      {d.length && (
        <p className={cn('text-sm', d.length.secs < d.length.min || d.length.secs > d.length.max ? 'text-red-300' : 'text-muted-foreground')}>
          Video ~{d.length.secs} giây, kể cả nghỉ giữa câu và outro (cần {d.length.min}–{d.length.max}), theo bản đã lưu.
        </p>
      )}

      {notice && <NoticeBox n={notice} />}

      {proposed && (
        <Alert className="border-emerald-500/30 bg-emerald-500/10 text-emerald-200">
          <Check />
          <AlertTitle>Có bản dịch đề xuất{differing ? `, khác ở ${differing} câu` : ''}</AlertTitle>
          <AlertDescription className="space-y-3 text-emerald-100/80">
            <p>Bản sửa nằm ở cột “Đề xuất”, chỗ khác bản hiện tại được tô xanh. “Dùng bản đề xuất” thay cả bản dịch hiện tại; “Bỏ” xóa bản đề xuất. Cả hai đều không hoàn lại được.</p>
            <div className="flex flex-wrap items-center gap-2">
              <Button size="lg" onClick={() => answer(true)} disabled={c.off || dirty}>
                {doing === 'proposal' ? <Loader2 className="animate-spin" /> : <Check />}
                Dùng bản đề xuất
              </Button>
              <Button variant="outline" size="lg" onClick={() => answer(false)} disabled={c.off || dirty}>
                Bỏ
              </Button>
              {dirty && <span className="text-xs">Lưu hoặc hoàn tác chỗ đang sửa trước.</span>}
            </div>
          </AlertDescription>
        </Alert>
      )}

      <Card className="gap-0 py-0">
        <Table className="md:table-fixed max-md:block">
          <TableHeader className="max-md:hidden">
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-12 px-2">Câu</TableHead>
              <TableHead className={cn('px-2', proposed ? 'w-[21%]' : 'w-[26%]')}>Tiếng Anh</TableHead>
              <TableHead className="px-2">Tiếng Việt</TableHead>
              {proposed && <TableHead className="w-[28%] px-2">Đề xuất</TableHead>}
              <TableHead className={cn('px-2', proposed ? 'w-[15%]' : 'w-[20%]')}>Ghi chú</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody className="max-md:block">
            {rows.map((r) => {
              const mark = flagged.has(r.id) && drafts[r.id] === undefined
              return (
                <TableRow key={r.id} className={cn('hover:bg-transparent max-md:block max-md:px-3 max-md:py-3', mark && 'bg-red-500/[0.06]')}>
                  <TableCell className={cn(CELL, 'font-mono text-xs text-muted-foreground md:text-sm md:pt-4')}>
                    <span className="md:hidden">Câu </span>
                    {r.id}
                  </TableCell>
                  <TableCell className={cn(CELL, 'text-sm text-muted-foreground md:pt-4')} lang="en">
                    {r.en}
                  </TableCell>
                  <TableCell className={cn(CELL)}>
                    <PhraseField id={r.id} value={drafts[r.id] ?? r.phrases} onChange={(v) => edit(r, v)} readOnly={c.off} invalid={mark} />
                  </TableCell>
                  {proposed && (
                    <TableCell className={cn(CELL, LABEL, !changes(r) && 'max-md:hidden')} data-label="Đề xuất">
                      <Proposal now={r} p={prop.get(r.id)} />
                    </TableCell>
                  )}
                  <TableCell className={cn(CELL, LABEL, 'text-xs text-amber-200/80 md:pt-4', !r.note && 'max-md:hidden')} data-label="Ghi chú">
                    {r.note}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </Card>

      {result &&
        (result.ok ? (
          <Alert className="border-emerald-500/30 bg-emerald-500/10 text-emerald-200">
            <CircleCheck />
            <AlertTitle>Đã lưu, kịch bản hợp lệ</AlertTitle>
          </Alert>
        ) : (
          <Alert className="border-red-500/30 bg-red-500/10 text-red-200">
            <TriangleAlert />
            <AlertTitle>Đã lưu, nhưng còn {result.problems.length || 'một số'} chỗ cần sửa</AlertTitle>
            <AlertDescription className="text-red-100/85">
              <ul className="list-disc space-y-1 pl-4 [overflow-wrap:anywhere]">
                {result.problems.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        ))}

      <div className="sticky bottom-0 z-10 -mx-4 border-t bg-background/90 px-4 py-3 backdrop-blur">
        <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-end gap-2">
          <span className="mr-auto basis-full text-xs text-muted-foreground empty:hidden sm:basis-auto">{why}</span>
          {dirty && !c.busy && (
            <Button variant="ghost" size="lg" onClick={() => setDrafts({})}>
              <Undo2 /> Hoàn tác
            </Button>
          )}
          <Button variant="outline" size="lg" onClick={save} disabled={c.off}>
            {doing === 'save' ? <Loader2 className="animate-spin" /> : <Save />}
            Lưu và kiểm
          </Button>
          <Button size="lg" onClick={approve} disabled={c.off || dirty || !!proposed}>
            {doing === 'approve' ? <Loader2 className="animate-spin" /> : <Check />}
            Duyệt bản dịch
          </Button>
        </div>
      </div>
    </div>
  )
}
