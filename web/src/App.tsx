// The shell: header, the relogin banner, hash routing (#/ is the list, #/r/<slug> one video), and the 5-second refresh.
import { useCallback, useEffect, useRef, useState } from 'react'
import { Clapperboard, KeyRound, LogIn, Loader2, WifiOff } from 'lucide-react'
import { toast } from 'sonner'
import { AccessCode } from '@/AccessCode'
import { AddTopics } from '@/AddTopics'
import { RunDetail } from '@/RunDetail'
import { RunList } from '@/RunList'
import { errorMessage, getState, onAccessLost, post, type State } from '@/api'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Toaster } from '@/components/ui/sonner'

const REFRESH_MS = 5000

type Route = { name: 'list' } | { name: 'run'; slug: string }

function parseHash(hash: string): Route {
  const m = hash.match(/^#\/r\/([^/?#]+)/)
  if (m) {
    try {
      return { name: 'run', slug: decodeURIComponent(m[1]) }
    } catch {
      /* a broken %-escape: the list */
    }
  }
  return { name: 'list' }
}

function useRoute(): Route {
  const [hash, setHash] = useState(location.hash)
  useEffect(() => {
    const on = () => {
      setHash(location.hash)
      scrollTo(0, 0) // a new page starts at its top
    }
    addEventListener('hashchange', on)
    return () => removeEventListener('hashchange', on)
  }, [])
  return parseHash(hash)
}

/** The state of the server, read now and every 5 seconds. A failed read keeps the last good state and says so. */
function useServerState() {
  const [state, setState] = useState<State | null>(null)
  const [failed, setFailed] = useState('')
  const [at, setAt] = useState<Date | null>(null)
  const latest = useRef(0)
  const pending = useRef(0)

  /** Read now. Used after a write or a login too: what was in flight before it may be older than the change. */
  const refresh = useCallback(async () => {
    const mine = ++latest.current // an older answer arriving late must not replace a newer one
    pending.current++
    try {
      const s = await getState()
      if (mine !== latest.current) return
      setState(s)
      setFailed('')
      setAt(new Date())
    } catch (e) {
      if (mine === latest.current) setFailed(errorMessage(e))
    } finally {
      pending.current--
    }
  }, [])

  useEffect(() => {
    // the timer asks only when no read is out: on a slow line reads would pile up, and every one but the last is thrown away
    const poll = () => document.hidden || pending.current || refresh()
    refresh()
    const tick = setInterval(poll, REFRESH_MS)
    document.addEventListener('visibilitychange', poll)
    return () => {
      clearInterval(tick)
      document.removeEventListener('visibilitychange', poll)
    }
  }, [refresh])

  return { state, failed, at, refresh }
}

function ReloginBanner({ state, refresh }: { state: State; refresh: () => void }) {
  const [busy, setBusy] = useState(false)
  const waiting = state.rows.filter((r) => state.relogin.includes(r.slug))
  const howTo = [...new Set(waiting.map((r) => r.message.trim()).filter(Boolean))]

  async function resume() {
    setBusy(true)
    try {
      await post('/api/resume')
      toast.success('Đã xếp các video này chạy tiếp')
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
      refresh()
    }
  }

  return (
    <Alert className="border-amber-500/30 bg-amber-500/10 text-amber-200">
      <LogIn />
      <AlertTitle className="text-amber-200">Hàng đợi tạm dừng: NotebookLM hết phiên đăng nhập</AlertTitle>
      <AlertDescription className="space-y-3 text-amber-100/80">
        <div className="flex flex-wrap items-center gap-1.5">
          Đang chờ:
          {state.relogin.map((s) => (
            <a key={s} href={`#/r/${encodeURIComponent(s)}`} className="rounded bg-amber-500/15 px-1.5 py-0.5 font-mono text-xs hover:bg-amber-500/25">
              {s}
            </a>
          ))}
        </div>
        {howTo.map((t) => (
          <div key={t} className="whitespace-pre-line">
            {t}
          </div>
        ))}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <Button variant="outline" size="sm" onClick={resume} disabled={!state.can_write || busy} className="border-amber-500/40 bg-transparent text-amber-100 hover:bg-amber-500/15">
            {busy && <Loader2 className="animate-spin" />}
            Chạy tiếp hàng đợi
          </Button>
          {!state.can_write && <span className="text-sm">Cần mã truy cập</span>}
        </div>
      </AlertDescription>
    </Alert>
  )
}

export default function App() {
  const route = useRoute()
  const { state, failed, at, refresh } = useServerState()

  // a write refused with 403: the code is gone or was changed. Read the state again so the code box shows.
  useEffect(() => {
    onAccessLost(refresh)
    return () => onAccessLost(null)
  }, [refresh])

  const running = state?.rows.filter((r) => r.state === 'running').length ?? 0

  return (
    <div className="min-h-svh bg-background">
      <header className="sticky top-0 z-20 border-b bg-background/90 backdrop-blur">
        <div className="mx-auto flex min-h-18 max-w-6xl flex-wrap items-center gap-3 px-6 py-3">
          <a href="#/" className="flex min-w-0 items-center gap-3 rounded-lg outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand text-white">
              <Clapperboard className="size-5" />
            </span>
            <span className="min-w-0 leading-tight">
              <span className="block text-base font-bold">vshort</span>
              <span className="block truncate text-sm text-muted-foreground">Bảng điều khiển video</span>
            </span>
          </a>
          <div className="ml-auto flex items-center gap-4 text-sm text-muted-foreground">
            {state && (
              <span className="flex items-center gap-2 rounded-full bg-card px-3 py-1.5">
                <span className={running ? 'size-2 rounded-full bg-brand-text' : 'size-2 rounded-full bg-faint'} aria-hidden />
                Đang chạy {running}/{state.max_running}
              </span>
            )}
            {state?.can_write && (
              <span className="flex items-center gap-1" title="Đã nhập mã truy cập">
                <KeyRound className="size-3.5" />
                <span className="hidden sm:inline">Đã nhập mã</span>
              </span>
            )}
          </div>
        </div>
        {failed && (
          <div role="alert" className="flex items-center justify-center gap-2 border-t border-destructive/30 bg-destructive/15 px-4 py-1.5 text-xs text-destructive">
            <WifiOff className="size-3.5 shrink-0" />
            <span>
              {failed}
              {state ? ': đang hiện dữ liệu lần cập nhật cuối, trang sẽ tự thử lại' : ': trang sẽ tự thử lại sau vài giây'}
            </span>
          </div>
        )}
      </header>

      <main className="mx-auto max-w-6xl space-y-6 px-6 py-6">
        {state && state.relogin.length > 0 && <ReloginBanner state={state} refresh={refresh} />}
        {state && !state.can_write && <AccessCode tokenSet={state.token_set} refresh={refresh} />}

        {/* hidden, not unmounted: a half-pasted list of topics survives a look at one video */}
        <div hidden={route.name !== 'list'} className="space-y-6">
          {state ? (
            <AddTopics canWrite={state.can_write} maxRunning={state.max_running} refresh={refresh} />
          ) : (
            <Skeleton className="h-44 rounded-xl" />
          )}
          <section className="space-y-4">
            <div className="flex items-end justify-between gap-3">
              <h1 className="text-xl font-semibold tracking-tight">Video</h1>
              {at && (
                <span className="text-xs text-muted-foreground">Cập nhật {at.toLocaleTimeString('vi-VN')}</span>
              )}
            </div>
            <RunList rows={state?.rows ?? null} canWrite={!!state?.can_write} refresh={refresh} />
          </section>
        </div>
        {route.name === 'run' && (
          <RunDetail
            key={route.slug} // another video starts from nothing: no draft or notice of the last one
            slug={route.slug}
            canWrite={!!state?.can_write}
            fallback={state?.rows.find((r) => r.slug === route.slug)}
            refreshState={refresh}
          />
        )}
      </main>
      <Toaster theme="dark" />
    </div>
  )
}
