"""Animated chat-story reel renderer (PIL frames -> ffmpeg), with synthesized UI sounds."""
import math, random, subprocess, sys, os, wave, json
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS, SR = 1080, 1920, 30, 48000
FD = "/usr/share/fonts/opentype/inter/"
F_MSG = ImageFont.truetype(FD + "Inter-Medium.otf", 50)
F_IN = ImageFont.truetype(FD + "Inter-Regular.otf", 46)
F_NAME = ImageFont.truetype(FD + "Inter-Bold.otf", 44)
F_STAT = ImageFont.truetype(FD + "Inter-Medium.otf", 32)
F_HOOK = ImageFont.truetype(FD + "InterDisplay-Black.otf", 78)
F_TAG = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 30)

BG = (14, 14, 17); PANEL = (24, 24, 29); AI_B = (44, 44, 52); HU_B = (52, 120, 246)
WHITE = (245, 245, 247); GREY = (150, 150, 160); GREEN = (80, 210, 120); YEL = (255, 225, 77)

AV = Image.open("/home/claude/chat/avatar.png").convert("RGBA").crop((28, 0, 372, 416))
AV_S = AV.resize((84, int(84 * AV.height / AV.width)), Image.LANCZOS)

# layout (keeps clear of Instagram's UI: top ~140, bottom ~420, right ~150)
HOOK_Y = 150
HEAD_Y = 470; HEAD_H = 130
CHAT_TOP = HEAD_Y + HEAD_H + 30; INPUT_Y = 1395; INPUT_H = 100
CHAT_BOT = INPUT_Y - 30
SIDE_L, SIDE_R = 70, 150
MAXW = 640

def ease_out_back(t, s=1.7):
    t = min(max(t, 0), 1) - 1
    return t * t * ((s + 1) * t + s) + 1

def ease_out(t):
    t = min(max(t, 0), 1); return 1 - (1 - t) ** 3

def wrap(text, font, maxw):
    words, lines, cur = text.split(" "), [], ""
    for w_ in words:
        test = (cur + " " + w_).strip()
        if font.getlength(test) <= maxw or not cur:
            cur = test
        else:
            lines.append(cur); cur = w_
    lines.append(cur); return lines

def bubble_img(text, who):
    lines = wrap(text, F_MSG, MAXW - 64)
    lh = 64
    tw = max(F_MSG.getlength(l) for l in lines)
    bw, bh = int(tw + 64), int(len(lines) * lh + 40)
    im = Image.new("RGBA", (bw, bh), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    col = HU_B if who == "human" else AI_B
    d.rounded_rectangle([0, 0, bw - 1, bh - 1], radius=40, fill=col)
    # tail corner
    if who == "human": d.rounded_rectangle([bw - 40, bh - 40, bw - 1, bh - 1], radius=10, fill=col)
    else: d.rounded_rectangle([0, bh - 40, 40, bh - 1], radius=10, fill=col)
    for i, l in enumerate(lines):
        d.text((32, 18 + i * lh), l, font=F_MSG, fill=WHITE)
    return im

def dots_img(t):
    bw, bh = 170, 92
    im = Image.new("RGBA", (bw, bh), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, bw - 1, bh - 1], radius=40, fill=AI_B)
    d.rounded_rectangle([0, bh - 40, 40, bh - 1], radius=10, fill=AI_B)
    for k in range(3):
        ph = (t * 2.6 - k * 0.18) % 1.0
        lift = math.sin(min(ph, 0.5) * 2 * math.pi) * 10 if ph < 0.5 else 0
        a = 255 if ph < 0.5 else 150
        cx = 50 + k * 35; cy = bh // 2 - lift
        d.ellipse([cx - 11, cy - 11, cx + 11, cy + 11], fill=(200, 200, 210, a))
    return im

# ---------------- timeline ----------------
def build_timeline(script, cps=19.0):
    """script items: ("human", text) typed in input box then sent; ("ai", text, typing_seconds); ("wait", s); ("punch",) marks last msg as punch."""
    t = -0.35; msgs = []; typing = []; dots = []; sounds = []; punch_t = None
    for it in script:
        kind = it[0]
        if kind == "wait":
            t += it[1]
        elif kind == "human":
            text = it[1]; start = t; dur = len(text) / cps
            typing.append((start, start + dur, text))
            for i, ch in enumerate(text):
                if ch != " ": sounds.append(("key", start + i / cps))
            t = start + dur + 0.22
            msgs.append(dict(who="human", text=text, t=t)); sounds.append(("send", t)); t += 0.35
        elif kind == "ai":
            text, tdur = it[1], it[2]
            dots.append((t, t + tdur)); t += tdur
            msgs.append(dict(who="ai", text=text, t=t)); sounds.append(("recv", t)); t += 0.45
        elif kind == "punch":
            msgs[-1]["punch"] = True; punch_t = msgs[-1]["t"]
            sounds[-1] = ("punch", punch_t)
    return msgs, typing, dots, sounds, punch_t, t

# ---------------- frame ----------------
def draw_static(hook_lines, hook_hi, tag):
    base = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(base)
    # subtle top glow
    glow = Image.new("RGB", (W, H), BG); gd = ImageDraw.Draw(glow)
    gd.ellipse([-300, -700, W + 300, 700], fill=(34, 32, 22)); glow = glow.filter(ImageFilter.GaussianBlur(160))
    base = Image.blend(base, glow, 0.85); d = ImageDraw.Draw(base)
    # tag + hook
    tw = d.textlength(tag, font=F_TAG)
    d.rounded_rectangle([SIDE_L, HOOK_Y, SIDE_L + tw + 36, HOOK_Y + 52], radius=10, fill=YEL)
    d.text((SIDE_L + 18, HOOK_Y + 9), tag, font=F_TAG, fill=(20, 20, 20))
    y = HOOK_Y + 78
    for ln in hook_lines:
        x = SIDE_L
        for word in ln.split(" "):
            wl = d.textlength(word, font=F_HOOK)
            hi = word.strip(".,!?").lower() in hook_hi
            if hi:
                d.rounded_rectangle([x - 10, y + 4, x + wl + 10, y + 92], radius=10, fill=YEL)
            d.text((x, y), word, font=F_HOOK, fill=(20, 20, 20) if hi else WHITE)
            x += wl + d.textlength(" ", font=F_HOOK) + (8 if hi else 0)
        y += 88
    # chat panel
    d.rounded_rectangle([40, HEAD_Y, W - 40, INPUT_Y + INPUT_H + 30], radius=48, fill=PANEL)
    d.line([40, HEAD_Y + HEAD_H, W - 40, HEAD_Y + HEAD_H], fill=(40, 40, 48), width=2)
    return base

def render_frame(t, static, msgs, typing, dots, punch_t):
    im = static.copy(); d = ImageDraw.Draw(im)
    # header
    base_y = HEAD_Y + (HEAD_H - AV_S.height) // 2
    im.paste(AV_S, (SIDE_L + 10, base_y), AV_S)
    nx = SIDE_L + 10 + AV_S.width + 26
    d.text((nx, HEAD_Y + 22), "AI Intern", font=F_NAME, fill=WHITE)
    is_typing = any(a <= t < b for a, b in dots)
    d.text((nx, HEAD_Y + 76), "typing…" if is_typing else "online", font=F_STAT, fill=GREEN if not is_typing else GREY)
    # messages layout (top-anchored, scroll when needed)
    visible = [m for m in msgs if t >= m["t"]]
    items = []  # (img, who, appear_t, punch)
    for m in visible:
        items.append((m["img"], m["who"], m["t"], m.get("punch")))
    dot_active = [(a, b) for a, b in dots if a <= t < b]
    total_h = sum(i[0].height + 22 for i in items) + (92 + 22 if dot_active else 0)
    avail = CHAT_BOT - CHAT_TOP
    # smooth scroll target
    over = max(0, total_h - avail)
    y = CHAT_TOP - over
    for img, who, at, pun in items:
        k = ease_out((t - at) / 0.22)
        sc = ease_out_back((t - at) / (0.32 if pun else 0.22), 2.4 if pun else 1.4)
        sc = 0.86 + 0.14 * sc if not pun else 0.6 + 0.4 * sc
        bi = img
        if abs(sc - 1) > 0.002:
            bi = img.resize((max(1, int(img.width * sc)), max(1, int(img.height * sc))), Image.BICUBIC)
        if k < 1:
            a = bi.getchannel("A").point(lambda v: int(v * k)); bi = bi.copy(); bi.putalpha(a)
        yo = int((1 - k) * 40)
        if who == "human":
            x = W - SIDE_R + 60 - img.width + (img.width - bi.width)
        else:
            x = SIDE_L + 10
        yy = y + yo + (img.height - bi.height) // 2
        if CHAT_TOP - 200 < yy < CHAT_BOT:
            im.paste(bi, (x, yy), bi)
        y += img.height + 22
    if dot_active:
        a0, _ = dot_active[0]
        di = dots_img(t - a0)
        k = ease_out((t - a0) / 0.15)
        di2 = di.copy(); di2.putalpha(di.getchannel("A").point(lambda v: int(v * k)))
        im.paste(di2, (SIDE_L + 10, y + int((1 - k) * 20)), di2)
    # cover anything scrolled above chat top (redraw header band)
    # input bar
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([SIDE_L, INPUT_Y, W - SIDE_R + 60, INPUT_Y + INPUT_H], radius=50, fill=(36, 36, 43))
    cur = ""; active = False
    for a, b, text in typing:
        if a <= t < b + 0.22:
            n = min(len(text), int((t - a) / (b - a) * len(text)) + 1) if t < b else len(text)
            cur = text[:n]; active = True
    if cur:
        shown = cur
        while F_IN.getlength(shown) > (W - SIDE_R + 60 - SIDE_L - 170) and len(shown) > 1: shown = shown[1:]
        d.text((SIDE_L + 40, INPUT_Y + 24), shown, font=F_IN, fill=WHITE)
        cx = SIDE_L + 40 + F_IN.getlength(shown) + 4
    else:
        d.text((SIDE_L + 40, INPUT_Y + 24), "Message…", font=F_IN, fill=(110, 110, 120)); cx = SIDE_L + 40
    if active and int(t * 2.2) % 2 == 0:
        d.rectangle([cx, INPUT_Y + 24, cx + 4, INPUT_Y + 78], fill=HU_B)
    sbx = W - SIDE_R + 60 - 84
    d.ellipse([sbx, INPUT_Y + 12, sbx + 76, INPUT_Y + 88], fill=HU_B if cur else (60, 60, 70))
    d.polygon([(sbx + 26, INPUT_Y + 32), (sbx + 56, INPUT_Y + 50), (sbx + 26, INPUT_Y + 68), (sbx + 32, INPUT_Y + 50)], fill=WHITE)
    # punch camera push
    if punch_t is not None and t >= punch_t:
        z = 1 + 0.06 * ease_out((t - punch_t) / 0.5)
        cw, ch = int(W / z), int(H / z)
        cx0 = (W - cw) // 2; cy0 = int((CHAT_TOP + CHAT_BOT) / 2 - ch / 2)
        cy0 = max(0, min(H - ch, cy0))
        im = im.crop((cx0, cy0, cx0 + cw, cy0 + ch)).resize((W, H), Image.BICUBIC)
    return im

# ---------------- audio ----------------
def synth(events, total):
    n = int(total * SR) + SR; out = np.zeros(n, dtype=np.float32); rng = np.random.default_rng(7)
    def add(sig, t, gain=1.0):
        i = int(t * SR)
        if i < 0: return
        j = min(n, i + len(sig)); out[i:j] += sig[: j - i] * gain
    for kind, t in events:
        if kind == "key":
            L = int(0.035 * SR); tt = np.arange(L) / SR
            noise = rng.standard_normal(L).astype(np.float32)
            click = noise * np.exp(-tt * 180) * 0.25 + np.sin(2 * np.pi * rng.uniform(1800, 2600) * tt) * np.exp(-tt * 260) * 0.15
            add(click.astype(np.float32), t, rng.uniform(0.6, 1.0))
        elif kind == "send":
            L = int(0.22 * SR); tt = np.arange(L) / SR
            f = 500 + 1600 * tt / 0.22
            sig = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * tt / 0.22) * 0.30
            add(sig.astype(np.float32), t)
        elif kind in ("recv", "punch"):
            g = 0.32 if kind == "recv" else 0.45
            for k, (f0, dt) in enumerate([(880, 0), (1320, 0.07)]):
                L = int(0.18 * SR); tt = np.arange(L) / SR
                sig = np.sin(2 * np.pi * f0 * tt) * np.exp(-tt * 22) * g
                add(sig.astype(np.float32), t + dt)
            if kind == "punch":
                L = int(0.25 * SR); tt = np.arange(L) / SR
                boom = np.sin(2 * np.pi * (90 - 40 * tt) * tt) * np.exp(-tt * 14) * 0.6
                add(boom.astype(np.float32), t)
    out = out[: int(total * SR)]
    peak = np.max(np.abs(out)) or 1; out = out / peak * 0.8
    return out

def write_wav(path, sig):
    st = np.repeat((sig * 32767).astype(np.int16)[:, None], 2, axis=1)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(st.tobytes())

def render(name, script, hook_lines, hook_hi, tag, hold=1.6, frames_only=None):
    msgs, typing, dots, sounds, punch_t, end = build_timeline(script)
    for m in msgs: m["img"] = bubble_img(m["text"], m["who"])
    total = round((end + hold) * FPS) / FPS
    static = draw_static(hook_lines, hook_hi, tag)
    if frames_only is not None:
        for ts in frames_only:
            render_frame(ts, static, msgs, typing, dots, punch_t).save(f"/home/claude/chat/prev_{name}_{ts:.2f}.png")
        return total
    tmp = f"/home/claude/chat/{name}.v.tmp.mp4"
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                          "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    for f in range(int(total * FPS)):
        p.stdin.write(render_frame(f / FPS, static, msgs, typing, dots, punch_t).tobytes())
    p.stdin.close(); assert p.wait() == 0
    wav = f"/home/claude/chat/{name}.wav"; write_wav(wav, synth(sounds, total))
    out = f"/home/claude/chat/{name}.tmp.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", "-movflags", "+faststart", out], check=True)
    os.rename(out, f"/home/claude/chat/{name}.mp4"); os.remove(tmp)
    return total

REEL1 = dict(
    script=[("human", "ok you're in charge of my instagram now"),
            ("ai", "Amazing. Posting your search history.", 0.9),
            ("wait", 0.15), ("human", "NO"),
            ("ai", "kidding :)", 0.55),
            ("ai", "…it's in drafts.", 1.3), ("punch",)],
    hook_lines=["I gave an AI my", "Instagram password."], hook_hi=["ai"], tag="DAY 1 / 30")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "preview":
        tot = render("reel1", **REEL1, frames_only=[0.0, 1.2, 3.0, 5.2, 7.2, 8.6])
        print("total", tot)
    else:
        print("total", render("reel1", **REEL1))
