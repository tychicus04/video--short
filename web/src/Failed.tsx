// A video that stopped: error (it failed and said why) or dead (its process is gone). Shows what it said, the log, and a way to run it again.
import { useState } from 'react'
import { Loader2, RotateCcw, TriangleAlert, Unplug } from 'lucide-react'
import { toast } from 'sonner'
import { errorMessage, post } from '@/api'
import { LogTail, Message, NoticeBox, runApi, type Ctx, type Notice } from '@/runKit'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export function Failed({ c }: { c: Ctx }) {
  const { row, log_tail } = c.d
  const dead = row.state === 'dead'
  const [retrying, setRetrying] = useState(false)
  const [notice, setNotice] = useState<Notice | null>(null)

  async function retry() {
    setNotice(null)
    setRetrying(true)
    try {
      await c.write(() => post(runApi(c, 'retry')))
      toast.success('Đã xếp video chạy lại')
    } catch (e) {
      setNotice({ kind: 'error', text: errorMessage(e) })
    } finally {
      setRetrying(false)
      await c.reload()
    }
  }

  return (
    <div className="space-y-4">
      <Alert className={dead ? 'border-orange-500/30 bg-orange-500/10 text-orange-200' : 'border-red-500/30 bg-red-500/10 text-red-200'}>
        {dead ? <Unplug /> : <TriangleAlert />}
        <AlertTitle>{dead ? 'Video dừng giữa chừng' : 'Video bị lỗi'}</AlertTitle>
        <AlertDescription className={cn(dead ? 'text-orange-100/85' : 'text-red-100/85')}>
          {dead && <p className="mb-2">Tiến trình chạy video không còn nữa nhưng chưa ghi kết quả.</p>}
          {row.message.trim() ? <Message text={row.message} /> : <p>Không có lời nhắn, xem nhật ký bên dưới.</p>}
        </AlertDescription>
      </Alert>

      {notice && <NoticeBox n={notice} />}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Button size="lg" className="w-full sm:w-auto" onClick={retry} disabled={c.off}>
          {retrying ? <Loader2 className="animate-spin" /> : <RotateCcw />}
          Chạy lại
        </Button>
        {!c.canWrite ? (
          <span className="text-sm text-muted-foreground">Cần mã truy cập</span>
        ) : row.relogin ? (
          <span className="text-sm text-muted-foreground">Đăng nhập lại NotebookLM theo hướng dẫn ở trên rồi mới bấm Chạy lại.</span>
        ) : (
          <span className="text-sm text-muted-foreground">Xếp vào hàng đợi và làm tiếp từ bước đang dở.</span>
        )}
      </div>

      <LogTail text={log_tail} />
    </div>
  )
}
