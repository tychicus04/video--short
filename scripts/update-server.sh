#!/bin/bash
# pve2 tự cập nhật khi rảnh: đợi tới lúc không có video nào chạy, rồi git pull, uv sync, build web nếu web/ đổi,
# khởi động lại vshort-web. Mac gọi qua `systemd-run --user --unit vshort-update` (xem push-outro.sh);
# chạy tay cũng được. Log: journalctl --user -u vshort-update
cd "$(dirname "$0")/.." || exit 1

busy() {  # có hàng chờ, có run đang chạy, có lệnh vshort đang chạy, hoặc một run vừa đổi file trong 10 phút
  pgrep -f "bin/vshort " >/dev/null && return 0
  ! .venv/bin/python - <<'EOF'
import sys, time
from vshort import queue
q = queue.load_queue()
running = q.new or q.resume or any(r["state"] in ("running", "queued") for r in queue.rows(q))
recent = any(f.stat().st_mtime > time.time() - 600
             for d in queue.runs_dir().iterdir() if d.is_dir() for f in d.rglob("*") if f.is_file())
sys.exit(1 if running or recent else 0)
EOF
}

main() {
  while busy; do echo "đang có video chạy, đợi 5 phút"; sleep 300; done
  old=$(git rev-parse HEAD)
  git pull -q --ff-only && uv sync -q || exit 1
  mkdir -p "$HOME/.claude/agents"  # the vs-* agents `vshort auto` calls by name: a deploy links every one, new ones too
  for f in "$PWD/claude/agents/"*.md; do ln -sf "$f" "$HOME/.claude/agents/$(basename "$f")"; done
  find "$HOME/.claude/agents" -maxdepth 1 -name 'vs-*.md' -xtype l -delete  # agents gone from the repo: no dangling links
  git diff --quiet "$old" HEAD -- web || (cd web && npm ci --silent && npm run build --silent) || exit 1
  systemctl --user restart vshort-web
  echo "đã cập nhật ${old:0:7} → $(git rev-parse --short HEAD)"
}
main; exit  # git pull may rewrite this file: bash has read all of main by now
