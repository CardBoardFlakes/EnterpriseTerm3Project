"""
Web wallpaper backend.

For genuinely smooth, GPU-accelerated animation we don't try to redraw the
desktop image ourselves — instead this app maintains two files that an
external "animated wallpaper" engine renders:

  * ``index.html`` — a self-contained <canvas> wallpaper that animates the
    current weather (rain, snow, drifting clouds, a moving sun, twinkling
    stars, lightning) using requestAnimationFrame;
  * ``weather.json`` — the live weather/theme state, rewritten only when it
    changes. The page polls it every couple of seconds and reacts.

Point any of these at ``index.html`` (its path is printed in the GUI):
  * ScreenPlay (Windows / macOS / Linux) — add as a Web wallpaper
  * Lively Wallpaper (Windows)          — add ``index.html`` as a wallpaper
  * Plash (macOS)                        — set the file:// URL as the website

The app's cost stays negligible (a tiny JSON write on change); all the
animation work happens in the wallpaper engine's own render loop, which those
tools already pause during fullscreen apps / on battery.
"""

import os
import json

import wallpaper

WEB_DIR = os.path.join(wallpaper.CACHE_DIR, "webwallpaper")
HTML_VERSION = "1"   # bump to force a rewrite of index.html on upgrade


def html_path() -> str:
    return os.path.join(WEB_DIR, "index.html")


def state_path() -> str:
    return os.path.join(WEB_DIR, "weather.json")


def file_url() -> str:
    """A file:// URL for the wallpaper page (handy for Plash / browsers)."""
    return "file://" + html_path().replace(os.sep, "/")


def build_state(r, g, b, brightness, condition, temperature,
                tint_strength=0.4, warmth=True, patterns=True) -> dict:
    """
    The JSON payload the page consumes. Gradient colours are computed with the
    same maths as the static PNG (`wallpaper.build_weather_image`) so the two
    backends look consistent; the page adds motion on top.
    """
    base = wallpaper.shifted_base(r, g, b, tint_strength, 0.0, 0.0)
    top = wallpaper._mix(base, (255, 255, 255), 0.18 * brightness)
    bottom = wallpaper._mix(base, (0, 0, 0), 0.45)
    wf = wallpaper.warmth_factor(temperature) if warmth else 0.0
    if wf > 0:
        top = wallpaper._mix(top, wallpaper.WARM_TINT, 0.22 * wf)
        bottom = wallpaper._mix(bottom, wallpaper.WARM_TINT, 0.14 * wf)
    return {
        "condition": (condition or "clear").lower(),
        "temperature": temperature,
        "brightness": round(brightness, 3),
        "warmth": round(wf, 3),
        "patterns": bool(patterns),
        "base": list(base),
        "top": list(top),
        "bottom": list(bottom),
    }


def write_state(state: dict) -> str:
    """Write *state* to weather.json atomically; returns the path."""
    os.makedirs(WEB_DIR, exist_ok=True)
    path = state_path()
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, path)
    return path


def ensure_assets() -> str:
    """Write index.html if missing or from an older version. Returns its path."""
    os.makedirs(WEB_DIR, exist_ok=True)
    path = html_path()
    marker = f"<!-- etc-wallpaper v{HTML_VERSION} -->"
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                if marker in f.read(256):
                    return path
        except OSError:
            pass
    with open(path, "w") as f:
        f.write(_INDEX_HTML.replace("__VERSION__", HTML_VERSION))
    return path


def open_folder() -> bool:
    """Best-effort: reveal the web-wallpaper folder in the OS file manager."""
    import sys
    import subprocess
    ensure_assets()
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", WEB_DIR], timeout=5)
        elif sys.platform == "win32":
            os.startfile(WEB_DIR)  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", WEB_DIR], timeout=5)
        return True
    except Exception as e:
        print(f"[webwall] Could not open folder: {e}")
        return False


# The wallpaper page. Self-contained (no external assets), so any engine that
# can render a local HTML file will show it. Kept dependency-free and modest on
# particle counts; requestAnimationFrame is naturally paused when the page is
# hidden (which wallpaper engines do during fullscreen / on battery).
_INDEX_HTML = r"""<!DOCTYPE html>
<!-- etc-wallpaper v__VERSION__ -->
<html><head><meta charset="utf-8"><title>Weather Wallpaper</title>
<style>html,body{margin:0;height:100%;overflow:hidden;background:#0b1020}
#c{display:block;width:100vw;height:100vh}</style></head>
<body><canvas id="c"></canvas>
<script>
const cvs=document.getElementById('c'),ctx=cvs.getContext('2d');
let W,H;function resize(){W=cvs.width=innerWidth;H=cvs.height=innerHeight;}
addEventListener('resize',resize);resize();
let S={condition:'clear',top:[120,170,255],bottom:[20,30,60],brightness:1,warmth:0,temperature:null};
let cond=null,parts=[],flash=0,last=0;
const R=(a,b)=>a+Math.random()*(b-a);
async function poll(){try{const r=await fetch('weather.json?_='+Date.now(),{cache:'no-store'});
  const j=await r.json();if(j&&j.condition)S=j;}catch(e){}}
poll();setInterval(poll,2000);
function build(){cond=S.condition;parts=[];const c=cond;
  if(c.includes('rain')||c.includes('storm')){const hv=c.includes('storm');
    const n=Math.round(W*(hv?0.09:0.06));
    for(let i=0;i<n;i++)parts.push({x:R(0,W),y:R(0,H),l:R(8,hv?22:16),v:R(hv?9:6,hv?16:11),sl:hv?2.2:1.2});}
  else if(c.includes('snow')){const n=Math.round(W*0.08);
    for(let i=0;i<n;i++)parts.push({x:R(0,W),y:R(0,H),r:R(1.5,3.5),v:R(1,3),d:R(-0.6,0.6),ph:R(0,6.28)});}
  else if(c.includes('night')){const n=Math.round(W*0.12);
    for(let i=0;i<n;i++)parts.push({x:R(0,W),y:R(0,H*0.9),r:R(0.5,1.6),ph:R(0,6.28),sp:R(0.6,2)});}
  else if(c.includes('cloud')){for(let i=0;i<5;i++)parts.push({x:R(0,W),y:R(H*0.15,H*0.7),r:R(70,150),v:R(4,12)});}}
function grad(){const g=ctx.createLinearGradient(0,0,0,H);
  g.addColorStop(0,'rgb('+S.top.join(',')+')');g.addColorStop(1,'rgb('+S.bottom.join(',')+')');
  ctx.fillStyle=g;ctx.fillRect(0,0,W,H);}
function sun(t,b,veiled){const cx=W*0.5+Math.sin(t/60000)*W*0.15,cy=H*0.28,rad=Math.min(W,H)*0.5;
  const g=ctx.createRadialGradient(cx,cy,0,cx,cy,rad);
  g.addColorStop(0,'rgba(255,240,200,'+(0.55*b)+')');g.addColorStop(1,'rgba(255,240,200,0)');
  ctx.fillStyle=g;ctx.beginPath();ctx.arc(cx,cy,rad,0,6.28);ctx.fill();
  if(!veiled){const rd=Math.min(W,H)*0.05*(1+0.03*Math.sin(t/500));
    ctx.fillStyle='rgba(255,250,225,'+(0.9*b)+')';ctx.beginPath();ctx.arc(cx,cy,rd,0,6.28);ctx.fill();}}
function blob(x,y,r){ctx.beginPath();ctx.ellipse(x,y,r,r*0.55,0,0,6.28);ctx.fill();
  ctx.beginPath();ctx.ellipse(x-r*0.5,y+r*0.12,r*0.6,r*0.4,0,0,6.28);ctx.fill();
  ctx.beginPath();ctx.ellipse(x+r*0.5,y+r*0.12,r*0.6,r*0.4,0,0,6.28);ctx.fill();}
function clouds(dt){ctx.fillStyle='rgba(247,242,236,0.32)';
  for(const p of parts){p.x+=p.v*dt*0.2;if(p.x-p.r>W)p.x=-p.r;blob(p.x,p.y,p.r);}}
function night(t,b){const mx=W*0.78,my=H*0.24,rad=Math.min(W,H)*0.25;
  let g=ctx.createRadialGradient(mx,my,0,mx,my,rad);
  g.addColorStop(0,'rgba(215,222,255,0.4)');g.addColorStop(1,'rgba(215,222,255,0)');
  ctx.fillStyle=g;ctx.beginPath();ctx.arc(mx,my,rad,0,6.28);ctx.fill();
  ctx.fillStyle='rgba(240,242,255,0.95)';ctx.beginPath();ctx.arc(mx,my,Math.min(W,H)*0.05,0,6.28);ctx.fill();
  for(const s of parts){const a=Math.max(0,0.4+0.5*Math.sin(t/700*s.sp+s.ph));
    ctx.fillStyle='rgba(255,255,255,'+a+')';ctx.beginPath();ctx.arc(s.x,s.y,s.r,0,6.28);ctx.fill();}}
function snow(dt){ctx.fillStyle='rgba(255,255,255,0.85)';
  for(const p of parts){p.y+=p.v*dt;p.x+=Math.sin(p.ph+p.y/40)*p.d;
    if(p.y>H){p.y=-4;p.x=R(0,W);}ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,6.28);ctx.fill();}}
function rain(dt,hv){ctx.strokeStyle='rgba(200,220,255,'+(hv?0.5:0.38)+')';ctx.lineWidth=hv?1.6:1.1;
  for(const p of parts){p.y+=p.v*dt;p.x+=p.sl*dt;if(p.y>H){p.y=-p.l;p.x=R(0,W);}if(p.x>W)p.x-=W;
    ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(p.x-p.sl*3,p.y-p.l);ctx.stroke();}}
function bolt(){ctx.strokeStyle='rgba(255,255,240,0.9)';ctx.lineWidth=2;
  let x=R(W*0.2,W*0.8),y=0;ctx.beginPath();ctx.moveTo(x,y);
  while(y<H*0.6){y+=R(15,35);x+=R(-25,25);ctx.lineTo(x,y);}ctx.stroke();}
function lightning(dt){if(Math.random()<0.006)flash=1;
  if(flash>0){ctx.fillStyle='rgba(255,255,255,'+(flash*0.35)+')';ctx.fillRect(0,0,W,H);
    if(flash>0.7)bolt();flash-=0.06*dt;if(flash<0)flash=0;}}
function frame(t){const dt=Math.min(50,t-last)/16.7;last=t;
  if(S.condition!==cond)build();grad();const c=S.condition,b=S.brightness;
  if(c.includes('clear'))sun(t,b,false);
  else if(c.includes('cloud')){sun(t,b*0.5,true);clouds(dt);}
  else if(c.includes('night'))night(t,b);
  else if(c.includes('snow'))snow(dt);
  if(c.includes('rain')||c.includes('storm'))rain(dt,c.includes('storm'));
  if(c.includes('storm'))lightning(dt);
  requestAnimationFrame(frame);}
document.addEventListener('visibilitychange',()=>{last=performance.now();});
requestAnimationFrame(frame);
</script></body></html>
"""
