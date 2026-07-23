#!/usr/bin/env python3
"""
Salaryse Asset Finder
Reads lib/util/constants/app_images.dart -> one self-contained searchable HTML gallery.
If hashes.json (from precompute_hashes.py) exists, adds drag-and-drop / upload
reverse image search (find the closest-looking existing assets).

Nothing is written into the app repo (only app_images.dart is read).

Usage:
    python3 build_gallery.py [<repo_root>]
"""

import re, os, sys, json, html

DEFAULT_REPO = os.environ.get("SALARYSE_APP", "/Users/ashvintiwari/Desktop/salaryse/salary_se_app")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "asset_gallery.html")
HASHES = os.path.join(HERE, "hashes.json")
THUMBS = os.path.join(HERE, "thumbs.json")
LOTTIE_SIGS = os.path.join(HERE, "lottie_sigs.json")
LOTTIE_LIB = os.path.join(HERE, "lottie.min.js")

ASSET_PREFIX = "assets/"
NETWORK_PREFIX = "https://assets.salaryse.com/"
CONST_RE = re.compile(r'static const\s+(\w+)\s*=\s*([^;]*?);', re.DOTALL)
STRING_RE = re.compile(r'"([^"]*)"')


def strip_comments(t):
    return "\n".join(l for l in t.splitlines() if not l.strip().startswith("//"))


def resolve(raw):
    m = STRING_RE.search(raw)
    if not m:
        return None
    return m.group(1).replace("${assetImagePath}", ASSET_PREFIX).replace("${networkImagePath}", NETWORK_PREFIX)


def ext_of(p):
    m = re.search(r'\.(\w+)(?:\?|$)', p)
    return m.group(1).lower() if m else "?"


def build_items(repo_root):
    with open(os.path.join(repo_root, "lib/util/constants/app_images.dart"), encoding="utf-8") as f:
        source = strip_comments(f.read())
    hashes = json.load(open(HASHES)) if os.path.exists(HASHES) else {}
    thumbs = json.load(open(THUMBS)) if os.path.exists(THUMBS) else {}
    sigs = json.load(open(LOTTIE_SIGS)) if os.path.exists(LOTTIE_SIGS) else {}
    seen = {}
    for name, raw in CONST_RE.findall(source):
        if name in ("assetImagePath", "networkImagePath"):
            continue
        path = resolve(raw)
        if not path:
            continue
        network = path.startswith("http")
        # prefer the embedded thumbnail (instant, no network); else S3 url / local file
        src = thumbs.get(name) or (path if network else "file://" + os.path.join(repo_root, path))
        seen[name] = {"name": name, "path": path, "src": src,
                      "ext": ext_of(path), "origin": "S3" if network else "local",
                      "hash": hashes.get(name), "lottieSig": sigs.get(name)}
    return sorted(seen.values(), key=lambda x: x["name"].lower()), len(hashes)


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Salaryse Asset Finder</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #0f1115; color: #e6e8eb; }
  header { position: sticky; top: 0; z-index: 10; background: #171a21; padding: 14px 20px; border-bottom: 1px solid #262b36; }
  h1 { font-size: 16px; margin: 0 0 10px; }
  h1 small { font-weight: 400; color: #8b93a1; }
  .controls { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
  #q { flex: 1; min-width: 220px; padding: 10px 14px; font-size: 15px; border-radius: 10px; border: 1px solid #2f3542; background: #0f1115; color: #e6e8eb; }
  select, .btn { padding: 10px 12px; border-radius: 10px; border: 1px solid #2f3542; background: #0f1115; color: #e6e8eb; cursor: pointer; font: inherit; }
  .btn:hover { border-color: #4b93f7; }
  #count { color: #8b93a1; font-size: 13px; margin-left: auto; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 14px; padding: 20px; }
  .card { background: #171a21; border: 1px solid #262b36; border-radius: 12px; padding: 10px; display: flex; flex-direction: column; gap: 8px; }
  .thumb { position: relative; height: 110px; display: flex; align-items: center; justify-content: center; background: repeating-conic-gradient(#20242e 0% 25%, #1a1d25 0% 50%) 50% / 20px 20px; border-radius: 8px; overflow: hidden; }
  .thumb img { max-width: 100%; max-height: 100%; object-fit: contain; }
  .thumb .fallback { display:none; position:absolute; inset:0; align-items:center; justify-content:center; color:#8b93a1; font-size:12px; text-align:center; padding:6px; flex-direction:column; }
  .thumb img.broken { display: none; }
  .thumb img.broken ~ .fallback { display: flex; }
  .sim { position:absolute; top:6px; right:6px; background:#0b3d2e; color:#6ee7b7; font-size:10px; font-weight:700; padding:2px 6px; border-radius:6px; }
  .name { font: inherit; font-size: 12px; font-weight: 600; color: #7dd3fc; background: none; border: none; text-align: left; cursor: pointer; padding: 0; word-break: break-all; }
  .name:hover { text-decoration: underline; }
  .name.copied { color: #34d399; }
  .meta { display: flex; gap: 6px; }
  .badge { font-size: 10px; padding: 2px 6px; border-radius: 5px; text-transform: uppercase; letter-spacing: .03em; }
  .badge.origin { background: #2a3140; color: #9aa3b2; }
  .badge.ext { background: #1f2b22; color: #86efac; }
  .path { font-size: 10px; color: #6b7280; word-break: break-all; }
  .empty { text-align:center; color:#8b93a1; padding: 60px 20px; }
  /* query banner */
  #queryBar { display:none; align-items:center; gap:12px; margin-top:10px; padding:10px 12px; background:#122036; border:1px solid #24406b; border-radius:10px; }
  #queryBar img { width:44px; height:44px; object-fit:contain; background:#0f1115; border-radius:8px; }
  #queryBar b { color:#cfe0ff; }
  #queryBar .btn { margin-left:auto; }
  /* full-screen drop overlay */
  #drop { display:none; position:fixed; inset:0; z-index:100; background:rgba(11,17,30,.92); border:3px dashed #4b93f7; align-items:center; justify-content:center; font-size:22px; color:#cfe0ff; }
  #drop.show { display:flex; }
  .hint { color:#6b7280; font-size:12px; }
</style>
</head>
<body>
<header>
  <h1>Salaryse Asset Finder <small>&middot; __TOTAL__ images (__LOCAL__ local &middot; __S3__ S3) &middot; __HASHED__ searchable by image</small></h1>
  <div class="controls">
    <input id="q" type="search" placeholder="Search by name or path... (e.g. prime video, arrow, upi)" autofocus>
    <select id="origin"><option value="">all sources</option><option value="local">local</option><option value="S3">S3</option></select>
    <select id="ext"><option value="">all types</option><option value="svg">svg</option><option value="png">png</option><option value="webp">webp</option><option value="json">lottie</option><option value="gif">gif</option></select>
    <button class="btn" id="uploadBtn">&#128247; Search by image / lottie</button>
    <input type="file" id="file" accept="image/*,.json,application/json" hidden>
    <span id="count"></span>
  </div>
  <div id="queryBar">
    <img id="queryImg" alt="query">
    <div id="qmsg">Closest matches &middot; <span class="hint">ranked by visual similarity</span></div>
    <button class="btn" id="clearQuery">&#10005; clear</button>
  </div>
  <div class="hint" id="dndHint" style="margin-top:8px">Tip: drag &amp; drop an image OR a lottie <code>.json</code> anywhere to find the closest existing assets.</div>
</header>
<div class="grid" id="grid"></div>
<div id="drop">&#11015; Drop image or lottie .json to find closest assets</div>
<script>__LOTTIE_LIB__</script>
<script>
  const DATA = __DATA__;
  const HAS_HASHES = DATA.some(d => d.hash);

  const grid = document.getElementById('grid');
  const q = document.getElementById('q');
  const originSel = document.getElementById('origin');
  const extSel = document.getElementById('ext');
  const count = document.getElementById('count');
  const queryBar = document.getElementById('queryBar');
  const queryImg = document.getElementById('queryImg');
  const qmsg = document.getElementById('qmsg');
  const fileInput = document.getElementById('file');

  let mode = 'text';        // 'text' | 'image'
  let ranked = [];          // items sorted by similarity when in image mode

  function fuzzy(n, h){ if(!n) return true; if(h.includes(n)) return true; let i=0; for(const c of h){ if(c===n[i]) i++; if(i===n.length) return true;} return false; }
  function tokens(s){ return s.trim().toLowerCase().split(/\s+/).filter(Boolean); }

  function card(it, sim){
    const simTag = (sim!==undefined) ? `<div class="sim">${sim}%</div>` : '';
    const fb = it.ext==='json' ? '&#127902; lottie' : '&#9888; preview blocked';
    return `<div class="card">
      <div class="thumb">${simTag}
        <img loading="lazy" src="${it.src}" alt="${it.name}" referrerpolicy="no-referrer" onerror="this.classList.add('broken')">
        <div class="fallback">${fb}<span>${it.ext}</span></div>
      </div>
      <button class="name" title="click to copy AppImages.${it.name}">AppImages.${it.name}</button>
      <div class="meta"><span class="badge origin">${it.origin}</span><span class="badge ext">${it.ext}</span></div>
      <div class="path">${it.path}</div>
    </div>`;
  }

  function paint(list, sims){
    if(!list.length){ grid.innerHTML='<div class="empty">No matches.</div>'; count.textContent='0 shown'; return; }
    grid.innerHTML = list.map((it,i)=>card(it, sims? sims[i]: undefined)).join('');
    grid.querySelectorAll('.name').forEach((btn,idx)=> btn.addEventListener('click',()=>copy(btn,'AppImages.'+list[idx].name)));
    count.textContent = list.length + ' shown';
  }

  function copy(btn,text){ navigator.clipboard.writeText(text); const o=btn.textContent; btn.textContent='✓ copied!'; btn.classList.add('copied'); setTimeout(()=>{btn.textContent=o;btn.classList.remove('copied');},1000); }

  function applyText(){
    const terms=tokens(q.value), origin=originSel.value, ext=extSel.value;
    const out=DATA.filter(it=>{
      if(origin && it.origin!==origin) return false;
      if(ext && it.ext!==ext) return false;
      const hay=(it.name+' '+it.path).toLowerCase();
      return terms.every(t=>fuzzy(t,hay));
    });
    paint(out);
  }

  // ---- reverse image search: 256-bit dHash, MUST match precompute_hashes.py ----
  function hexToBits(hex){ return BigInt('0x'+hex); }          // 64 hex chars -> BigInt
  function hamming(a,b){ let x=a^b, c=0n; while(x){ c += x & 1n; x >>= 1n; } return Number(c); }

  function grayFromCtx(ctx,w,h){
    const d=ctx.getImageData(0,0,w,h).data, g=new Float64Array(w*h);
    for(let i=0;i<w*h;i++) g[i]=d[i*4]*0.299+d[i*4+1]*0.587+d[i*4+2]*0.114;   // PIL 'L' luma
    return g;
  }
  function newCanvas(w,h){ const c=document.createElement('canvas'); c.width=w; c.height=h; return c; }

  function stddev(a){ let m=0; for(const v of a)m+=v; m/=a.length; let s=0; for(const v of a)s+=(v-m)*(v-m); return Math.sqrt(s/a.length); }

  function dhashOfImage(img){
    // 1. draw on transparent canvas, composite on white; if colourless on white,
    //    fall back to the alpha silhouette (matches dhash_of_cell in Python)
    const maxd=256; let iw=img.naturalWidth||img.width||64, ih=img.naturalHeight||img.height||64;
    const s=Math.min(1,maxd/Math.max(iw,ih)); let w=Math.max(1,Math.round(iw*s)), h=Math.max(1,Math.round(ih*s));
    const cv=newCanvas(w,h), ctx=cv.getContext('2d',{willReadFrequently:true});
    ctx.clearRect(0,0,w,h); ctx.drawImage(img,0,0,w,h);
    const d=ctx.getImageData(0,0,w,h).data;
    let g=new Float64Array(w*h); const alpha=new Float64Array(w*h);
    for(let i=0;i<w*h;i++){ const a=d[i*4+3]/255;
      const r=d[i*4]*a+255*(1-a), gg=d[i*4+1]*a+255*(1-a), b=d[i*4+2]*a+255*(1-a);
      g[i]=r*0.299+gg*0.587+b*0.114; alpha[i]=d[i*4+3]; }
    if(stddev(g)<6 && stddev(alpha)>=3) g=alpha.slice();   // silhouette
    // 2. polarity: if background (border) is dark, invert so bg is light
    let bsum=0,bn=0;
    for(let x=0;x<w;x++){ bsum+=g[x]+g[(h-1)*w+x]; bn+=2; }
    for(let y=0;y<h;y++){ bsum+=g[y*w]+g[y*w+w-1]; bn+=2; }
    if(bsum/bn<128) for(let i=0;i<g.length;i++) g[i]=255-g[i];
    // 3. trim to content (pixels clearly darker than light background)
    let minx=w,miny=h,maxx=-1,maxy=-1;
    for(let y=0;y<h;y++)for(let x=0;x<w;x++) if(g[y*w+x]<240){ if(x<minx)minx=x; if(x>maxx)maxx=x; if(y<miny)miny=y; if(y>maxy)maxy=y; }
    let cw=w,ch=h,cg=g;
    if(maxx>=minx){ cw=maxx-minx+1; ch=maxy-miny+1; cg=new Float64Array(cw*ch);
      for(let y=0;y<ch;y++)for(let x=0;x<cw;x++) cg[y*cw+x]=g[(y+miny)*w+(x+minx)]; }
    // 4. min-max stretch
    let mn=255,mx=0; for(const v of cg){ if(v<mn)mn=v; if(v>mx)mx=v; }
    if(mx>mn){ const sc=255/(mx-mn); for(let i=0;i<cg.length;i++) cg[i]=(cg[i]-mn)*sc; }
    // 5. hand-written bilinear resize to 17x16 (MUST match _resize_bilinear in Python)
    const fg=resizeBilinear(cg,cw,ch);
    // 6. dHash 256-bit, MSB-first
    let val=0n;
    for(let row=0;row<16;row++)for(let col=0;col<16;col++){ const i=row*17+col; val=(val<<1n)|((fg[i]<fg[i+1])?1n:0n); }
    return val;
  }

  function resizeBilinear(cg,cw,ch){
    const TW=17,TH=16,out=new Float64Array(TW*TH);
    for(let ty=0;ty<TH;ty++){ let sy=(ty+0.5)*ch/TH-0.5; let y0=Math.floor(sy),fy=sy-y0;
      let y0c=Math.min(Math.max(y0,0),ch-1), y1c=Math.min(Math.max(y0+1,0),ch-1);
      for(let tx=0;tx<TW;tx++){ let sx=(tx+0.5)*cw/TW-0.5; let x0=Math.floor(sx),fx=sx-x0;
        let x0c=Math.min(Math.max(x0,0),cw-1), x1c=Math.min(Math.max(x0+1,0),cw-1);
        const v00=cg[y0c*cw+x0c],v10=cg[y0c*cw+x1c],v01=cg[y1c*cw+x0c],v11=cg[y1c*cw+x1c];
        const top=v00*(1-fx)+v10*fx, bot=v01*(1-fx)+v11*fx;
        out[ty*TW+tx]=top*(1-fy)+bot*fy;
      }}
    return out;
  }

  function visualRank(img){
    const qh=dhashOfImage(img);
    return DATA.filter(it=>it.hash).map(it=>({it, d: hamming(qh, hexToBits(it.hash))})).sort((a,b)=>a.d-b.d);
  }

  function runImageSearch(dataUrl){
    if(!HAS_HASHES){ alert('Image search needs precomputed hashes (run precompute_hashes.py).'); return; }
    const img=new Image();
    img.onload=()=>{
      ranked=visualRank(img).slice(0,60);
      mode='image';
      queryImg.src=dataUrl; queryBar.style.display='flex';
      qmsg.innerHTML='Closest matches &middot; <span class="hint">ranked by visual similarity</span>';
      paint(ranked.map(r=>r.it), ranked.map(r=>Math.round((1-r.d/256)*100)));
    };
    img.src=dataUrl;
  }

  // ---- lottie: structural signature (MUST match lottie_sig() in Python) ----
  function lottieSig(d){
    const w=parseInt(d.w||0)||0, h=parseInt(d.h||0)||0;
    const fr=Math.round(parseFloat(d.fr||0)||0), op=Math.round(parseFloat(d.op||0)||0), ip=Math.round(parseFloat(d.ip||0)||0);
    const layers=d.layers||[];
    const names=layers.map(l=>String(l.nm||'')).sort().join('~');
    const assets=(d.assets||[]).length;
    return w+'x'+h+'|fr'+fr+'|ip'+ip+'|op'+op+'|L'+layers.length+'|A'+assets+'|'+names;
  }

  function lottieFrameDataURL(obj, cb){
    if(typeof lottie==='undefined'){ cb(null); return; }
    const c=document.createElement('div');
    c.style.cssText='position:fixed;left:-9999px;top:0;width:160px;height:160px';
    document.body.appendChild(c);
    let a;
    try{ a=lottie.loadAnimation({container:c,renderer:'svg',loop:false,autoplay:false,animationData:obj}); }
    catch(e){ c.remove(); cb(null); return; }
    a.addEventListener('DOMLoaded',()=>{
      try{ a.goToAndStop(Math.floor(a.totalFrames*0.5),true); }catch(e){}
      requestAnimationFrame(()=>{
        const svg=c.querySelector('svg');
        let url=null;
        if(svg){ const xml=new XMLSerializer().serializeToString(svg);
          url='data:image/svg+xml;base64,'+btoa(unescape(encodeURIComponent(xml))); }
        a.destroy(); c.remove(); cb(url);
      });
    });
  }

  function runLottieSearch(text){
    let obj; try{ obj=JSON.parse(text); }catch(e){ alert('That file is not valid JSON.'); return; }
    const sig=lottieSig(obj);
    const exact=DATA.filter(d=>d.lottieSig && d.lottieSig===sig);
    lottieFrameDataURL(obj,(url)=>{
      let merged=[], sims=[];
      const exactNames=new Set(exact.map(e=>e.name));
      exact.forEach(e=>{ merged.push(e); sims.push(100); });
      const finish=()=>{
        mode='image';
        queryBar.style.display='flex';
        qmsg.innerHTML = exact.length
          ? ('&#9989; This animation ALREADY EXISTS as: <b>'+exact.map(e=>'AppImages.'+e.name).join(', ')+'</b>')
          : '&#128269; No identical animation found &middot; <span class="hint">showing visually closest</span>';
        paint(merged.slice(0,60), sims.slice(0,60));
      };
      if(url){
        const img=new Image();
        img.onload=()=>{ queryImg.src=url;
          visualRank(img).filter(r=>!exactNames.has(r.it.name)).slice(0,60-merged.length)
            .forEach(r=>{ merged.push(r.it); sims.push(Math.round((1-r.d/256)*100)); });
          finish();
        };
        img.onerror=finish; img.src=url;
      } else { queryImg.removeAttribute('src'); finish(); }
    });
  }

  function handleFile(file){
    if(!file) return;
    if(file.type==='application/json' || /\.json$/i.test(file.name||'')){
      const fr=new FileReader(); fr.onload=e=>runLottieSearch(e.target.result); fr.readAsText(file); return;
    }
    if(!file.type || file.type.startsWith('image/')){
      const fr=new FileReader(); fr.onload=e=>runImageSearch(e.target.result); fr.readAsDataURL(file);
    }
  }

  document.getElementById('uploadBtn').addEventListener('click',()=>fileInput.click());
  fileInput.addEventListener('change',e=>handleFile(e.target.files[0]));
  document.getElementById('clearQuery').addEventListener('click',()=>{ mode='text'; queryBar.style.display='none'; applyText(); });

  q.addEventListener('input',()=>{ if(mode==='image'){ mode='text'; queryBar.style.display='none'; } applyText(); });
  originSel.addEventListener('change',()=> mode==='image'?null:applyText());
  extSel.addEventListener('change',()=> mode==='image'?null:applyText());

  // drag & drop anywhere
  const drop=document.getElementById('drop');
  let dragDepth=0;
  window.addEventListener('dragenter',e=>{ e.preventDefault(); dragDepth++; drop.classList.add('show'); });
  window.addEventListener('dragover',e=>e.preventDefault());
  window.addEventListener('dragleave',e=>{ dragDepth--; if(dragDepth<=0) drop.classList.remove('show'); });
  window.addEventListener('drop',e=>{ e.preventDefault(); dragDepth=0; drop.classList.remove('show');
    const f=e.dataTransfer.files[0];
    if(f) return handleFile(f);
    // support dragging an <img> from another tab (url)
    const url=e.dataTransfer.getData('text/uri-list')||e.dataTransfer.getData('text/plain');
    if(url) runImageSearch(url);
  });
  // paste an image from clipboard
  window.addEventListener('paste',e=>{ const it=[...(e.clipboardData?.items||[])].find(i=>i.type.startsWith('image/')); if(it) handleFile(it.getAsFile()); });

  applyText();
</script>
</body>
</html>"""


def main():
    repo_root = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_REPO
    items, hashed = build_items(repo_root)
    total = len(items)
    s3 = sum(1 for i in items if i["origin"] == "S3")
    local = total - s3
    lottie_lib = open(LOTTIE_LIB).read() if os.path.exists(LOTTIE_LIB) else ""
    lottie_count = sum(1 for i in items if i.get("lottieSig"))
    doc = (TEMPLATE.replace("__TOTAL__", str(total)).replace("__LOCAL__", str(local))
           .replace("__S3__", str(s3)).replace("__HASHED__", str(hashed))
           .replace("__LOTTIE_LIB__", lottie_lib)
           .replace("__DATA__", json.dumps(items)))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"Gallery: {OUT}")
    print(f"  {total} images ({local} local, {s3} S3); {hashed} searchable by image; "
          f"{lottie_count} lotties with signatures")


if __name__ == "__main__":
    main()
