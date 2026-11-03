// A video waiting for its brief to be approved (wait_brief). NotebookLM makes the video from the English brief, so the two
// briefs must say the same thing: saving the Vietnamese one asks a cheap agent to bring the English one in line.
import { useEffect, useState } from 'react'
import { Check, ChevronDown, Languages, Loader2, Save, Undo2 } from 'lucide-react'
import { toast } from 'sonner'
import { ApiError, errorMessage, post } from '@/api'
import { NoticeBox, runApi, useUnsaved, type Ctx, type Notice } from '@/runKit'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

const Unsaved = () => (
  <Badge variant="outline" className="border-amber-500/30 bg-amber-500/10 text-amber-300">
    Chưa lưu
  </Badge>
)

export function BriefReview({ c }: { c: Ctx }) {
  const { d } = c
  const serverVi = d.brief_vi ?? ''
  const serverEn = d.brief_en ?? ''
  const stale = d.brief_en_stale

  // null: not edited, the page shows the file. A draft is kept until the file says the same.
  const [viDraft, setViDraft] = useState<string | null>(null)
  const [enDraft, setEnDraft] = useState<string | null>(null)
  const [enOpen, setEnOpen] = useState(stale)
  const [syncing, setSyncing] = useState(false) // the Vietnamese brief is out: the agent may take a minute or two
  const [approving, setApproving] = useState(false)
  const [notice, setNotice] = useState<Notice | null>(null)

  const viDirty = viDraft !== null && viDraft !== serverVi
  const enDirty = enDraft !== null && enDraft !== serverEn
  useEffect(() => {
    if (viDraft === serverVi) setViDraft(null)
  }, [viDraft, serverVi])
  useEffect(() => {
    if (enDraft === serverEn) setEnDraft(null)
  }, [enDraft, serverEn])
  useUnsaved(c, viDirty || enDirty)

  async function saveVi() {
    setNotice(null)
    setSyncing(true)
    try {
      const r = await c.write(() => post(runApi(c, 'brief'), { vi: viDraft ?? serverVi }))
      setEnOpen(true) // to read what the agent changed
      if (r?.brief_en_stale) {
        setNotice({ kind: 'warn', title: 'Bản tiếng Anh vẫn chưa được cập nhật', text: 'Đã lưu bản tiếng Việt. Sửa tay bản tiếng Anh bên dưới cho khớp, rồi bấm “Lưu bản tiếng Anh”.' })
      } else {
        toast.success('Đã lưu và cập nhật bản tiếng Anh')
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 502 && typeof e.data?.error === 'string') {
        // the agent failed; the Vietnamese brief IS saved, and saving the same text again would not ask the agent twice
        setEnOpen(true)
        setNotice({
          kind: 'warn',
          title: 'Chưa cập nhật được bản tiếng Anh',
          text: `${e.error}\n\nSửa tay bản tiếng Anh bên dưới cho khớp bản tiếng Việt, rồi bấm “Lưu bản tiếng Anh”.`,
        })
      } else if (e instanceof ApiError && (e.status === 0 || e.status >= 500)) {
        setEnOpen(true)
        setNotice({
          kind: 'error',
          text: `${e.error}. Chưa biết bản tiếng Việt đã được lưu chưa. Xem lại hai bản bên dưới; nếu bản tiếng Anh cũ hơn thì sửa tay rồi bấm “Lưu bản tiếng Anh”.`,
        })
      } else {
        setNotice({ kind: 'error', text: errorMessage(e) })
      }
    } finally {
      setSyncing(false)
      await c.reload()
    }
  }

  async function saveEn() {
    setNotice(null)
    try {
      await c.write(() => post(runApi(c, 'brief_en'), { en: enDraft ?? serverEn }))
      toast.success('Đã lưu bản tiếng Anh')
    } catch (e) {
      setNotice({ kind: 'error', text: errorMessage(e) })
    } finally {
      await c.reload()
    }
  }

  async function approve() {
    setNotice(null)
    setApproving(true)
    try {
      await c.write(() => post(runApi(c, 'approve'), { what: 'brief' }))
      toast.success('Đã duyệt brief, video quay lại hàng đợi')
    } catch (e) {
      setNotice({ kind: 'error', text: errorMessage(e) }) // the CLI's own message, or "không đang chờ duyệt bước này"
    } finally {
      setApproving(false)
      await c.reload()
    }
  }

  const unsaved = viDirty || enDirty
  const canApprove = !c.off && !stale && !unsaved && !!d.brief_en

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Đọc brief, sửa nếu cần rồi duyệt. NotebookLM làm video từ <strong className="font-medium text-foreground">bản tiếng Anh</strong>.
      </p>

      {notice && <NoticeBox n={notice} />}

      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">
            Brief tiếng Việt {viDirty && <Unsaved />}
          </CardTitle>
          <CardDescription>Sửa ở đây. Bấm lưu thì một agent nhỏ chỉnh bản tiếng Anh cho khớp những chỗ bạn đổi.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Textarea
            value={viDraft ?? serverVi}
            onChange={(e) => setViDraft(e.target.value)}
            readOnly={c.off}
            aria-label="Brief tiếng Việt"
            spellCheck={false}
            className="min-h-72 leading-6"
          />
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <Button size="lg" className="h-10 w-full sm:w-auto" onClick={saveVi} disabled={c.off || !viDirty}>
              {syncing ? <Loader2 className="animate-spin" /> : <Languages />}
              Lưu và cập nhật bản tiếng Anh
            </Button>
            {viDirty && !c.busy && (
              <Button variant="ghost" size="lg" onClick={() => setViDraft(null)}>
                <Undo2 /> Hoàn tác
              </Button>
            )}
            {syncing && (
              <span role="status" className="text-sm text-sky-300">
                Đang cập nhật bản tiếng Anh… có thể mất 1–2 phút, đừng đóng trang.
              </span>
            )}
            {!c.canWrite && <span className="text-sm text-muted-foreground">Cần mã truy cập</span>}
          </div>
        </CardContent>
      </Card>

      <Card className="gap-0 py-0">
        <button
          type="button"
          aria-expanded={enOpen}
          aria-controls="brief-en"
          onClick={() => setEnOpen(!enOpen)}
          className="flex w-full items-center gap-3 px-4 py-3 text-left outline-none hover:bg-accent/40 focus-visible:bg-accent/40"
        >
          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-center gap-2 font-medium">
              Bản tiếng Anh
              {stale && (
                <Badge variant="outline" className="border-amber-500/30 bg-amber-500/10 text-amber-300">
                  Cũ hơn bản tiếng Việt
                </Badge>
              )}
              {enDirty && <Unsaved />}
            </span>
            <span className="block text-xs text-muted-foreground">NotebookLM đọc bản này để làm video</span>
          </span>
          <ChevronDown aria-hidden className={cn('size-4 shrink-0 text-muted-foreground transition-transform', enOpen && 'rotate-180')} />
        </button>
        {enOpen && (
          <div id="brief-en" className="space-y-3 border-t px-4 py-4">
            <Textarea
              value={enDraft ?? serverEn}
              onChange={(e) => setEnDraft(e.target.value)}
              readOnly={c.off}
              aria-label="Brief tiếng Anh"
              spellCheck={false}
              className="min-h-64 font-mono text-xs leading-5 md:text-xs"
            />
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
              <Button variant="outline" size="lg" className="h-10 w-full sm:w-auto" onClick={saveEn} disabled={c.off || (!enDirty && !stale)}>
                <Save /> Lưu bản tiếng Anh
              </Button>
              {enDirty && !c.busy && (
                <Button variant="ghost" size="lg" onClick={() => setEnDraft(null)}>
                  <Undo2 /> Hoàn tác
                </Button>
              )}
              {stale && !enDirty && <span className="text-xs text-muted-foreground">Bản tiếng Anh vẫn đúng? Bấm lưu để xác nhận.</span>}
            </div>
          </div>
        )}
      </Card>

      <Card size="sm" className="bg-amber-500/[0.04] ring-amber-500/20">
        <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0 space-y-1 text-sm">
            <div className="font-medium">Brief đã ổn?</div>
            {stale && <p className="text-amber-200">Bản tiếng Anh cũ hơn bản tiếng Việt — NotebookLM làm video từ bản tiếng Anh</p>}
            {unsaved && <p className="text-muted-foreground">Còn chỗ sửa chưa lưu: lưu hoặc hoàn tác trước khi duyệt.</p>}
            {!c.canWrite && <p className="text-muted-foreground">Cần mã truy cập</p>}
            {!stale && !unsaved && c.canWrite && <p className="text-muted-foreground">Duyệt xong, video quay lại hàng đợi và chạy tiếp.</p>}
          </div>
          <Button size="lg" className="h-10 w-full shrink-0 sm:w-auto" onClick={approve} disabled={!canApprove}>
            {approving ? <Loader2 className="animate-spin" /> : <Check />}
            Duyệt brief
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
