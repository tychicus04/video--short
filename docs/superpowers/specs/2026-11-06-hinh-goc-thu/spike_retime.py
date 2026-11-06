# THROWAWAY spike: Vietnamese voice over NotebookLM's own moving video (clean.mp4), retimed per sentence.
# usage: python3 spike_retime.py RUN_DIR OUT.mp4 CUT_SECONDS
import json, subprocess, sys
from pathlib import Path

run, out, cut = Path(sys.argv[1]), Path(sys.argv[2]), float(sys.argv[3])
en = json.load(open(run / "sentences.en.json"))
vi = json.load(open(run / "timeline.json"))["placements"]
assert [e["id"] for e in en] == [p["id"] for p in vi]
FAST = 1.5  # most speed-up before the tail of a source span is dropped instead

n = len(en)
src = [(0.0 if i == 0 else en[i]["start"], en[i + 1]["start"] if i + 1 < n else en[i]["end"]) for i in range(n)]
tgt = [(0.0 if i == 0 else vi[i]["start"], vi[i + 1]["start"] if i + 1 < n else cut) for i in range(n)]

parts = []
for i, ((s0, s1), (t0, t1)) in enumerate(zip(src, tgt)):
    S, T = s1 - s0, t1 - t0
    if S >= T:  # Vietnamese is shorter: speed up, capped
        r = min(S / T, FAST)
        f = f"trim={s0:.3f}:{s0 + r * T:.3f},setpts=(PTS-STARTPTS)/{r:.4f}"
    else:  # Vietnamese is longer: play at 1x, then hold the last frame
        r = 1.0
        f = f"trim={s0:.3f}:{s1:.3f},setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={T - S + 0.1:.3f}"
    parts.append(f"[0:v]{f},fps=30,trim=duration={T:.3f},setpts=PTS-STARTPTS[v{i}]")
    print(f"{i + 1:2d} src {S:5.2f}s -> {T:5.2f}s  speed {r:.2f}" + ("" if S >= T else f"  hold {T - S:.2f}s"))

fonts = Path.home() / "video-pipeline/assets/fonts"
graph = ";".join(parts) + ";" + "".join(f"[v{i}]" for i in range(n)) + \
    f"concat=n={n}:v=1:a=0,ass={run / 'subs.ass'}:fontsdir={fonts},format=yuv420p[v];" \
    f"[1:a]atrim=0:{cut},asetpts=PTS-STARTPTS,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(run / "clean.mp4"), "-i", str(run / "narration.wav"),
                "-filter_complex", graph, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18",
                "-preset", "medium", "-c:a", "aac", "-b:a", "160k", "-ac", "1", str(out.with_suffix(".body.mp4"))],
               check=True)
outro = Path.home() / "video-pipeline/assets/brand/anm-outro.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(out.with_suffix(".body.mp4")), "-i", str(outro),
                "-filter_complex", "[1:a]aresample=48000,aformat=channel_layouts=mono[oa];[0:v][0:a][1:v][oa]concat=n=2:v=1:a=1[v][a]",
                "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-b:a", "160k",
                "-movflags", "+faststart", str(out)], check=True)
print("ok", out)
