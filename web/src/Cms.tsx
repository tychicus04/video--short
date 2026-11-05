// The "Gửi lên CMS" box at the end of the tab Đăng bài: one button that sends the finished video to the CMS as a personal,
// unpublished article and proposes the social posts (vshort cms). The send runs on the server; the box shows cms.json as
// the 5-second refresh brings it.
import { useEffect, useState } from 'react'
import { Check, Circle, Dot, ExternalLink, Loader2, Send, X } from 'lucide-react'
import { toast } from 'sonner'
import { ApiError, post, type CmsStepStatus } from '@/api'
import { NoticeBox, runApi, type Ctx } from '@/runKit'
import { Button } from '@/components/ui/button'

function Mark({ status }: { status: CmsStepStatus }) {
  if (status === 'done') return <Check className="size-4 shrink-0 text-ok" aria-label="xong" />
  if (status === 'running') return <Dot className="size-4 shrink-0 scale-[2] text-brand-text" aria-label="đang chạy" />
  if (status === 'error') return <X className="size-4 shrink-0 text-err-text" aria-label="lỗi" />
  return <Circle className="size-3 shrink-0 text-faint" aria-label={status === 'skip' ? 'bỏ qua' : 'chưa tới'} />
}

export function CmsBox({ c }: { c: Ctx }) {
  const { cms } = c.d
  const rec = cms.record
  const [confirm, setConfirm] = useState(false) // "Tạo bài mới" asks twice, without window.confirm
  useEffect(() => {
    if (!confirm) return
    const t = setTimeout(() => setConfirm(false), 5000)
    return () => clearTimeout(t)
  }, [confirm])

  const sending = cms.running
  const stopped = rec.state === 'running' && !sending // the process died midway
  const posted = rec.article_id != null
  const off = c.off || sending || !cms.configured
  const link = rec.link?.startsWith('https://') ? rec.link : null

  async function send(recreate: boolean) {
    setConfirm(false)
    try {
      await c.write(() => post(runApi(c, 'cms'), recreate ? { recreate: true } : {}))
      toast.success('Đã bắt đầu gửi')
    } catch (e) {
      toast.error(e instanceof ApiError ? e.error : 'Không gửi được')
    } finally {
      await c.reload()
    }
  }

  return (
    <section aria-labelledby="cms-h" className="space-y-4 rounded-lg bg-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="cms-h" className="text-lg font-semibold">
          Gửi lên CMS
        </h2>
        {cms.env === 'dev' && <span className="rounded-full bg-wait-bg px-3 py-1 text-[13px] font-semibold text-wait">Bản thử (dev)</span>}
        {cms.env === 'prod' && <span className="rounded-full bg-err/15 px-3 py-1 text-[13px] font-semibold text-err-text">Bản thật</span>}
      </div>

      {!cms.configured ? (
        <div className="space-y-1.5 text-sm">
          <p>Chưa cấu hình CMS trên máy chủ:</p>
          <ul className="list-disc space-y-1 pl-5 text-muted-foreground [overflow-wrap:anywhere]">
            {cms.missing.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          Tạo bài cá nhân chưa xuất bản (tiêu đề, sapo, 2 ảnh đại diện, video, chuyên mục, từ khóa) và đề xuất bài Facebook, YouTube,
          TikTok. Bạn tự xuất bản và duyệt bài mạng xã hội trong CMS.
        </p>
      )}

      {rec.steps && rec.steps.length > 0 && (
        <ul className="space-y-1.5 text-sm">
          {rec.steps.map((s) => (
            <li key={s.key} className="flex items-center gap-2.5">
              <Mark status={stopped && s.status === 'running' ? 'error' : s.status} />
              <span className={s.status === 'next' || s.status === 'skip' ? 'text-muted-foreground' : 'text-foreground'}>{s.label}</span>
              {s.status === 'skip' && <span className="text-xs text-faint">bỏ qua</span>}
            </li>
          ))}
        </ul>
      )}

      {rec.state === 'done' && posted && (
        <div className="space-y-1 text-sm">
          <p className="font-semibold">Bài số {rec.article_id}</p>
          {rec.proposal && <p className="text-muted-foreground">Đề xuất mạng xã hội: đã gửi, duyệt trong CMS</p>}
        </div>
      )}
      {stopped && <NoticeBox n={{ kind: 'error', text: 'Dừng giữa chừng. Bấm Gửi lại để làm tiếp từ việc dở.' }} />}
      {!stopped && rec.message && ['left', 'deleted', 'unsure', 'error'].includes(rec.state ?? '') && (
        <NoticeBox n={{ kind: rec.state === 'left' ? 'warn' : 'error', text: rec.message }} />
      )}
      {rec.warning && <NoticeBox n={{ kind: 'warn', text: rec.warning }} />}

      <div className="flex flex-wrap items-center gap-2">
        <Button disabled={off} onClick={() => send(false)}>
          {sending ? <Loader2 className="animate-spin" /> : <Send />}
          {sending ? 'Đang gửi…' : posted || stopped ? 'Gửi lại' : 'Gửi lên CMS'}
        </Button>
        {(rec.state === 'deleted' || rec.state === 'unsure') && (
          <Button variant="outline" disabled={off} onClick={() => (confirm ? send(true) : setConfirm(true))}>
            {confirm ? 'Bấm lần nữa để tạo bài mới' : 'Tạo bài mới'}
          </Button>
        )}
        {link && (
          <Button asChild variant="outline">
            <a href={link} target="_blank" rel="noreferrer noopener">
              <ExternalLink /> Mở bài trong CMS
            </a>
          </Button>
        )}
      </div>
      {!c.canWrite && <p className="text-sm text-muted-foreground">Cần mã truy cập để gửi.</p>}
    </section>
  )
}
