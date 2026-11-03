// Shown while this browser cannot write: one box for the shared access code. Reading never needs it.
import { useState, type FormEvent } from 'react'
import { KeyRound, Loader2 } from 'lucide-react'
import { errorMessage, post } from '@/api'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'

export function AccessCode({ tokenSet, refresh }: { tokenSet: boolean; refresh: () => void }) {
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!code.trim()) return
    setBusy(true)
    setError('')
    try {
      await post('/api/login', { token: code.trim() })
      setCode('')
      refresh()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="gap-3">
      <div className="flex items-start gap-3 px-4">
        <div className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground">
          <KeyRound className="size-4" />
        </div>
        <div className="min-w-0">
          <h2 className="text-sm font-medium">Cần mã truy cập</h2>
          <p className="text-sm text-muted-foreground">
            {tokenSet
              ? 'Xem thì không cần mã. Muốn thêm chủ đề, duyệt hay sửa thì nhập mã truy cập.'
              : 'Máy chủ chưa có file mã truy cập (web_token_file trong config.toml) nên chưa ghi được gì. Tạo file đó rồi tải lại trang.'}
          </p>
        </div>
      </div>
      {tokenSet && (
        <form onSubmit={submit} className="flex flex-col gap-2 px-4 sm:flex-row">
          <div className="flex-1">
            <Input
              type="password"
              name="access-code"
              autoComplete="off"
              placeholder="Mã truy cập"
              aria-label="Mã truy cập"
              aria-invalid={error ? true : undefined}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="h-9"
            />
            {error && <p className="mt-1.5 text-sm text-destructive">{error}</p>}
          </div>
          <Button type="submit" size="lg" disabled={busy || !code.trim()}>
            {busy && <Loader2 className="animate-spin" />}
            Nhập mã
          </Button>
        </form>
      )}
    </Card>
  )
}
