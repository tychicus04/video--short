#!/bin/zsh
# LaunchAgent vn.tai.vshort-outro chạy file này mỗi khi assets/brand/ đổi. Nếu anm-outro.mp4 khác bản đã commit
# và đọc được: commit riêng file đó, push, rồi bảo pve2 cập nhật khi rảnh (scripts/update-server.sh).
cd "${0:A:h}/.." || exit 1
f=assets/brand/anm-outro.mp4
say() { echo "$(date '+%F %T') $1"; osascript -e "display notification \"$1\" with title \"vshort outro\""; }

until [[ -z $(echo assets/brand/*.tmp.*(N)) && $(stat -f%z.%m $f 2>/dev/null) == $seen ]]; do  # đợi chép/vẽ xong
  seen=$(stat -f%z.%m $f 2>/dev/null); sleep 3
done
[[ -f $f ]] && ! git diff --quiet HEAD -- $f || exit 0  # không đổi (hoặc chính git vừa ghi lại nó)
.venv/bin/python -c "import sys; from vshort.media import probe; assert probe(sys.argv[1]).duration > 0" $f 2>/dev/null \
  || { say "anm-outro.mp4 mới không phải video đọc được, chưa đẩy"; exit 1; }
[[ $(git symbolic-ref --short HEAD) == main ]] || { say "repo không ở nhánh main, chưa đẩy outro"; exit 1; }

git commit -q -m "outro: thay anm-outro.mp4" -- $f || exit 1
git pull -q --rebase --autostash || { git rebase --abort 2>/dev/null; say "git pull lỗi, outro mới mới commit, chưa push"; exit 1; }
git push -q || { say "push lỗi, outro mới mới commit"; exit 1; }
ssh -o BatchMode=yes -o ConnectTimeout=20 pve2 'systemctl --user is-active -q vshort-update ||
  systemd-run --user --unit vshort-update --collect -E PATH="$PATH" ~/video-pipeline/scripts/update-server.sh' >/dev/null 2>&1 \
  || { say "đã push outro mới nhưng không gọi được pve2, nhớ cập nhật tay"; exit 1; }
say "đã đẩy outro mới, pve2 cập nhật khi không có video chạy"  # một lần cập nhật đang đợi sẵn cũng pull luôn bản này
