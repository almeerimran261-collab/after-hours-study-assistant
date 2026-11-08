import streamlit as st


def render_brand():
    pause_class = (
        "cn-paused"
        if st.session_state.get("cosmos_pause", False)
        else ""
    )

    markup = """
<style>
.cn-logo {
    width:48px;
    height:48px;
    flex:0 0 48px;
    display:grid;
    place-items:center;
    cursor:default;
}
.cn-saturn {
    width:48px;
    height:48px;
    overflow:visible;
    transition:transform .3s ease,filter .3s ease;
}
.cn-logo:hover .cn-saturn {
    transform:rotate(7deg) scale(1.06);
    filter:drop-shadow(0 0 8px rgba(196,181,253,.5));
}
.cn-orbit-dot {
    transform-origin:32px 32px;
    animation:cn-orbit 20s linear infinite;
}
.cn-paused .cn-orbit-dot {
    animation-play-state:paused;
}
@keyframes cn-orbit {
    from {transform:rotate(0deg);}
    to {transform:rotate(360deg);}
}
@media(prefers-reduced-motion:reduce) {
    .cn-orbit-dot {animation:none;}
    .cn-saturn {transition:none;}
    .cn-logo:hover .cn-saturn {transform:none;}
}
</style>

<div class="brand PAUSE_CLASS">
  <div class="cn-logo" aria-hidden="true">
    <svg class="cn-saturn"
         viewBox="0 0 64 64"
         xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="cn-sidebar-planet"
                        x1="0%" y1="0%"
                        x2="100%" y2="100%">
          <stop offset="0%" stop-color="#E5DBFF"/>
          <stop offset="100%" stop-color="#9A84CF"/>
        </linearGradient>
      </defs>

      <g transform="rotate(-25 32 32)">
        <ellipse cx="32" cy="32" rx="25" ry="9"
                 fill="none" stroke="#AD99E3"
                 stroke-width="3"/>

        <circle cx="32" cy="32" r="13"
                fill="url(#cn-sidebar-planet)"/>

        <path d="M7 32 A25 9 0 0 0 57 32"
              fill="none" stroke="#E8DFFF"
              stroke-width="3"
              stroke-linecap="round"/>
      </g>

      <g class="cn-orbit-dot">
        <circle cx="59" cy="32" r="2.5"
                fill="#F2BD82"/>
      </g>
    </svg>
  </div>

  <div>
    <strong>Course Notes</strong>
    <small>AFTER HOURS</small>
  </div>
</div>
"""

    html = " ".join(
        line.strip()
        for line in markup.replace(
            "PAUSE_CLASS", pause_class
        ).splitlines()
    )

    st.sidebar.markdown(
        html,
        unsafe_allow_html=True,
    )