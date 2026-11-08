import streamlit as st
from streamlit.components.v2 import component


CSS = """
<style>
body {background:#070916!important;}
#root {
    position: relative;
    z-index: 1;
    height: 100vh;
    height: 100dvh;
}
.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
    background:transparent!important;
}
[data-testid="stHeader"],
[data-testid="stBottom"],
[data-testid="stBottom"]>div,
[data-testid="stBottomBlockContainer"] {
    background:transparent!important;
}
[data-testid="stSidebar"] {
    background:rgba(11,13,31,.96)!important;
    border-color:#2c2945;
}
.hero {
    background:rgba(12,15,35,.43)!important;
    border-color:rgba(185,165,244,.22)!important;
}
.hero .eyebrow,.doc span,.brand small {
    color:#c4b5fd!important;
}
.hero p,.stat span,.section-label {
    color:#b3b7d1!important;
}
.brand-mark {
    background:#c4b5fd!important;color:#171129!important;
}
.stat,.doc {
    background:rgba(13,17,39,.80)!important;
    border-color:rgba(185,165,244,.20)!important;
}
[data-testid="stChatMessage"] {
    background:rgba(10,14,31,.95)!important;
    border-color:#302e4a!important;
}
[data-testid="stChatMessage"]:has(
    [data-testid="stChatMessageAvatarUser"]
) {
    background:rgba(26,24,49,.96)!important;
}
[data-testid="stButton"] button {
    background:rgba(15,18,39,.9);border-color:#3b3556;
}
[data-testid="stButton"] button:hover {
    border-color:#c4b5fd!important;
}
[data-testid="stChatInput"] {
    background:rgba(12,15,33,.98)!important;
    border-color:#6b5f91!important;
}
.source-badge {
    color:#dfd3ff!important;
    background:#28203c!important;
    border-color:#59466f!important;
}
</style>
"""


JS = r"""
export default function({data}) {
  const key = '__courseNotesCosmos';
  if (window[key]) window[key].destroy();

  const saved = window.__courseNotesCosmosTime ||= {seconds: 0};
  const canvas = document.createElement('canvas');
  canvas.setAttribute('aria-hidden', 'true');
  canvas.id = 'course-notes-cosmos';
  canvas.style.cssText =
    'position:fixed;inset:0;z-index:0;pointer-events:none;';
  document.body.appendChild(canvas);

  const ctx = canvas.getContext('2d');
  const sky = document.createElement('canvas');
  const sc = sky.getContext('2d');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const touch = matchMedia('(pointer: coarse)');

  // Radius, size, period, starting angle, highlight, shadow.
    const planetNames = [
    'Mercury', 'Venus', 'Earth', 'Mars',
    'Jupiter', 'Saturn', 'Uranus', 'Neptune'
  ];
  const planets = [
    [55, 3.5, 55, 2.2, '#d5c8bf', '#746965'],
    [95, 6.5, 85, 5.3, '#f0cf94', '#ac7946'],
    [145, 7.5, 120, .6, '#8ed2fa', '#2b62a3'],
    [195, 5, 170, 3.7, '#df9b7b', '#934a3d'],
    [260, 14, 230, 3.9, '#e9d7bb', '#a67e65'],
    [330, 12, 310, 1.7, '#e0cfae', '#9b8a77'],
    [400, 9, 400, 3.5, '#a7d5dc', '#558c9b'],
    [475, 8, 520, 1.2, '#93a7f1', '#405591']
  ];

  let w=0, h=0, dpr=1, frame=0, last=0, dead=false;
  let mouse={x:-1000, y:-1000, blocked:false};
  let shift={x:0, y:0};
  const tilt=-.24;

  const moving=()=>
    !data?.paused &&
    !reduce.matches &&
    !touch.matches &&
    !document.hidden;

  const orbit=(r,a)=>{
    const x=r*Math.cos(a), y=r*.42*Math.sin(a);
    return {
      x:x*Math.cos(tilt)-y*Math.sin(tilt),
      y:x*Math.sin(tilt)+y*Math.cos(tilt)
    };
  };

  function resize() {
    w=innerWidth;
    h=innerHeight;
    dpr=Math.min(devicePixelRatio||1,1.25);

    canvas.width=sky.width=Math.round(w*dpr);
    canvas.height=sky.height=Math.round(h*dpr);
    canvas.style.width=w+'px';
    canvas.style.height=h+'px';

    ctx.setTransform(dpr,0,0,dpr,0,0);
    sc.setTransform(dpr,0,0,dpr,0,0);
    sc.fillStyle='#070916';
    sc.fillRect(0,0,w,h);

    const clouds=[
      [.84,.16,.6,'rgba(91,61,153,.19)'],
      [.4,.88,.5,'rgba(88,49,88,.13)']
    ];

    for (const [x,y,r,c] of clouds) {
      const g=sc.createRadialGradient(w*x,h*y,0,w*x,h*y,w*r);
      g.addColorStop(0,c);
      g.addColorStop(1,'transparent');
      sc.fillStyle=g;
      sc.fillRect(0,0,w,h);
    }

    let seed=91;
    const random=()=>{
      seed=(seed*16807)%2147483647;
      return seed/2147483647;
    };

    for(let i=0;i<115;i++) {
      const x=random()*w, y=random()*h;
      const r=.35+random()*.9;
      sc.fillStyle=`rgba(213,219,255,${.15+random()*.48})`;
      sc.beginPath();
      sc.arc(x,y,r,0,Math.PI*2);
      sc.fill();
    }

    schedule();
  }

  function draw(ts) {
    frame=0;
    if(dead || document.hidden) return;

    const animate=moving();
    if(animate && last && ts-last<1000/30) {
      schedule();
      return;
    }

    if(animate && last) {
      saved.seconds+=Math.min((ts-last)/1000,.1);
    }
    last=ts;

    const targetX=reduce.matches||touch.matches||mouse.x<0
      ? 0
      : (Math.max(0,Math.min(1,mouse.x/w))-.5)*16;

    const targetY=reduce.matches||touch.matches||mouse.y<0
      ? 0
      : (Math.max(0,Math.min(1,mouse.y/h))-.5)*12;

    shift.x=animate ? shift.x+(targetX-shift.x)*.09 : targetX;
    shift.y=animate ? shift.y+(targetY-shift.y)*.09 : targetY;

    ctx.clearRect(0,0,w,h);
    ctx.drawImage(sky,0,0,w,h);

    const scale=Math.min(Math.max(w/1366,.48),1.15);
    const cx=w*(w<700?.64:.78)+shift.x;
    const cy=h*.57+shift.y;

    const positions=planets.map((p)=>{
      const angle=p[3]+saved.seconds*Math.PI*2/p[2];
      const v=orbit(p[0]*scale,angle);
      return {x:cx+v.x,y:cy+v.y,r:p[1]*scale};
    });

    let hovered=-1;
    if(!mouse.blocked && !touch.matches) {
      let nearest=Infinity;
      positions.forEach((p,i)=>{
        const distance=Math.hypot(mouse.x-p.x,mouse.y-p.y);
        if(distance<p.r+7 && distance<nearest) {
          nearest=distance;
          hovered=i;
        }
      });
    }

    planets.forEach((p,i)=>{
      ctx.strokeStyle=i===hovered
        ? 'rgba(207,187,255,.43)'
        : 'rgba(181,166,224,.13)';
      ctx.lineWidth=i===hovered?1.1:.7;
      ctx.beginPath();
      ctx.ellipse(
        cx,cy,p[0]*scale,p[0]*scale*.42,
        tilt,0,Math.PI*2
      );
      ctx.stroke();
    });

    const glow=ctx.createRadialGradient(
      cx,cy,0,cx,cy,90*scale
    );
    glow.addColorStop(0,'rgba(255,186,104,.32)');
    glow.addColorStop(.4,'rgba(243,142,83,.08)');
    glow.addColorStop(1,'transparent');
    ctx.fillStyle=glow;
    ctx.beginPath();
    ctx.arc(cx,cy,90*scale,0,Math.PI*2);
    ctx.fill();

    const sun=ctx.createRadialGradient(
      cx-5*scale,cy-5*scale,0,cx,cy,17*scale
    );
    sun.addColorStop(0,'#fff1cb');
    sun.addColorStop(.5,'#edb56d');
    sun.addColorStop(1,'#b66b3f');
    ctx.fillStyle=sun;
    ctx.beginPath();
    ctx.arc(cx,cy,17*scale,0,Math.PI*2);
    ctx.fill();

    positions.forEach((p,i)=>{
      const r=p.r*(i===hovered?1.18:1);

      if(i===hovered) {
        const halo=ctx.createRadialGradient(
          p.x,p.y,r,p.x,p.y,r*3
        );
        halo.addColorStop(0,'rgba(202,179,255,.35)');
        halo.addColorStop(1,'transparent');
        ctx.fillStyle=halo;
        ctx.beginPath();
        ctx.arc(p.x,p.y,r*3,0,Math.PI*2);
        ctx.fill();
      }

      if(i===5) {
        ctx.strokeStyle='#b6a9c4';
        ctx.lineWidth=2*scale;
        ctx.beginPath();
        ctx.ellipse(
          p.x,p.y,r*1.9,r*.52,-.32,0,Math.PI*2
        );
        ctx.stroke();
      }

      const shade=ctx.createRadialGradient(
        p.x-r*.4,p.y-r*.4,0,
        p.x+r*.3,p.y+r*.3,r*1.5
      );
      shade.addColorStop(0,planets[i][4]);
      shade.addColorStop(.58,planets[i][5]);
      shade.addColorStop(1,'#101222');
      ctx.fillStyle=shade;
      ctx.beginPath();
      ctx.arc(p.x,p.y,r,0,Math.PI*2);
      ctx.fill();

      if(i===hovered) {
        ctx.strokeStyle='rgba(222,206,255,.85)';
        ctx.lineWidth=1;
        ctx.beginPath();
        ctx.arc(p.x,p.y,r+3,0,Math.PI*2);
        ctx.stroke();
      }
    });

    if(hovered >= 0) {
      const label = planetNames[hovered];

      ctx.font = '500 12px system-ui, sans-serif';
      ctx.textBaseline = 'middle';

      const boxWidth = Math.ceil(
        ctx.measureText(label).width
      ) + 20;
      const boxHeight = 28;

      const x = Math.max(
        8,
        Math.min(w - boxWidth - 8, mouse.x + 14)
      );
      const y = Math.max(
        8,
        Math.min(
          h - boxHeight - 8,
          mouse.y - boxHeight - 12
        )
      );

      ctx.fillStyle = 'rgba(14, 15, 34, .96)';
      ctx.strokeStyle = 'rgba(196, 181, 253, .55)';
      ctx.lineWidth = 1;

      ctx.beginPath();
      ctx.roundRect(x, y, boxWidth, boxHeight, 8);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = '#f0eaff';
      ctx.fillText(
        label,
        x + 10,
        y + boxHeight / 2
      );
    }

    if(animate) schedule();
  }

  function schedule() {
    if(!dead && !frame && !document.hidden) {
      frame=requestAnimationFrame(draw);
    }
  }

  function pointer(e) {
    if(e.pointerType && e.pointerType!=='mouse') return;

    const controls=(
      'button,input,textarea,select,a,[role="button"],' +
      '[data-testid="stChatMessage"],' +
      '[data-testid="stSidebar"]'
    );

    mouse={
      x:e.clientX,
      y:e.clientY,
      blocked:!!e.target.closest?.(controls)
    };
    schedule();
  }

  function leave() {
    mouse={x:-1000,y:-1000,blocked:false};
    schedule();
  }

  function visibility() {
    if(frame) cancelAnimationFrame(frame);
    frame=0;
    last=0;
    schedule();
  }

  function destroy() {
    if(dead) return;
    dead=true;
    if(frame) cancelAnimationFrame(frame);
    canvas.remove();

    window.removeEventListener('resize',resize);
    document.removeEventListener('pointermove',pointer);
    document.removeEventListener('pointerleave',leave);
    document.removeEventListener('visibilitychange',visibility);
    reduce.removeEventListener('change',visibility);
    touch.removeEventListener('change',visibility);
  }

  const controller={destroy};
  window[key]=controller;

  window.addEventListener('resize',resize);
  document.addEventListener(
    'pointermove',pointer,{passive:true}
  );
  document.addEventListener(
    'pointerleave',leave,{passive:true}
  );
  document.addEventListener(
    'visibilitychange',visibility
  );
  reduce.addEventListener('change',visibility);
  touch.addEventListener('change',visibility);

  resize();

  return ()=>{
    destroy();
    if(window[key]===controller) delete window[key];
  };
}
"""


def mount_cosmos():
    st.markdown(CSS, unsafe_allow_html=True)

    paused = st.sidebar.checkbox(
        "Pause wallpaper",
        key="cosmos_pause",
        help="Pause the orbits. Planet highlighting remains decorative.",
    )

    wallpaper = component("course_notes_cosmos", js=JS)
    wallpaper(
        data={"paused": paused},
        key="cosmos_wallpaper",
        height=0,
    )