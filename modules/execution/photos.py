"""Photo capture UI components for execution page."""

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from supabase import Client

from shared.helpers import bytes_from_camera_or_upload
from modules.execution.crud import photo_add, photos_for_req, photo_delete_slot


def _camera_facing_toggle(rid: str) -> str:
    """전후면 카메라 토글 — 단일 버튼. session_state 'cam_facing_<rid>' 저장.

    버튼 라벨:
        현재 후면 → "🔄 전면으로 전환  (현재: 📷 후면)"
        현재 전면 → "🔄 후면으로 전환  (현재: 🤳 전면)"

    Returns:
        "environment" (후면, 기본) | "user" (전면)
    """
    key = f"cam_facing_{rid}"
    if key not in st.session_state:
        st.session_state[key] = "environment"  # 현장 작업용 기본 = 후면
    facing = st.session_state[key]

    if facing == "environment":
        label = "🔄 전면으로 전환  (현재: 📷 후면)"
        next_facing = "user"
    else:
        label = "🔄 후면으로 전환  (현재: 🤳 전면)"
        next_facing = "environment"

    if st.button(
        label,
        key=f"cam_btn_toggle_{rid}",
        type="secondary",
        use_container_width=True,
    ):
        st.session_state[key] = next_facing
        st.rerun()

    st.caption(
        "💡 PC 노트북은 보통 웹캠 1개라 전환 효과가 없습니다. "
        "모바일/태블릿(전후면 카메라 보유)에서 사용하세요."
    )
    return facing


def _inject_camera_facing_js(facing: str) -> None:
    """st.camera_input의 카메라 facingMode를 강제 적용.

    3중 전략 (위에서부터 순차):
      1. parent window의 navigator.mediaDevices.getUserMedia를 monkey-patch
         → Streamlit이 다음 번 getUserMedia를 호출할 때 facingMode가 자동 주입
      2. 활성 video 트랙들을 stop() → Streamlit이 새로 getUserMedia 호출하도록 유도
      3. 활성 트랙에 applyConstraints({facingMode}) — fallback

    PC 노트북(웹캠 1개)에서는 효과가 없을 수 있음 — 모바일/태블릿에서 검증 필요.
    브라우저 DevTools 콘솔에 "[camera-toggle]" 로그가 나옴.
    """
    components.html(f"""
<script>
(function() {{
  const target = "{facing}";
  const tag = "[camera-toggle]";

  function patchGetUserMedia(win) {{
    try {{
      const md = win.navigator && win.navigator.mediaDevices;
      if (!md || !md.getUserMedia) {{ console.warn(tag, "no mediaDevices"); return false; }}
      if (!md.__origGetUserMedia) {{
        md.__origGetUserMedia = md.getUserMedia.bind(md);
        console.log(tag, "monkey-patched getUserMedia");
      }}
      md.getUserMedia = function(constraints) {{
        try {{
          constraints = constraints || {{}};
          if (constraints.video === undefined) constraints.video = true;
          if (constraints.video === true)     constraints.video = {{}};
          if (typeof constraints.video === 'object') {{
            constraints.video.facingMode = {{ ideal: window.__camTargetFacing || target }};
          }}
          console.log(tag, "getUserMedia →", JSON.stringify(constraints));
        }} catch(e) {{ console.warn(tag, "patch err", e); }}
        return md.__origGetUserMedia(constraints);
      }};
      win.__camTargetFacing = target;
      return true;
    }} catch(e) {{ console.warn(tag, "patch failed", e); return false; }}
  }}

  function stopTracks(win) {{
    try {{
      const videos = win.document.querySelectorAll('[data-testid="stCameraInput"] video');
      let count = 0;
      videos.forEach(v => {{
        if (v.srcObject && v.srcObject.getTracks) {{
          v.srcObject.getTracks().forEach(t => {{
            try {{ t.stop(); count++; }} catch(_){{}}
          }});
        }}
      }});
      if (count > 0) console.log(tag, "stopped", count, "tracks");
      return count;
    }} catch(e) {{ console.warn(tag, "stopTracks err", e); return 0; }}
  }}

  function applyToActive(win) {{
    try {{
      const videos = win.document.querySelectorAll('[data-testid="stCameraInput"] video');
      videos.forEach(v => {{
        if (v.srcObject && v.srcObject.getTracks) {{
          v.srcObject.getTracks().forEach(t => {{
            if (t.kind !== 'video' || !t.applyConstraints) return;
            t.applyConstraints({{ facingMode: {{ ideal: target }} }})
              .then(() => console.log(tag, "applyConstraints OK →", target))
              .catch(e => console.warn(tag, "applyConstraints failed", e));
          }});
        }}
      }});
    }} catch(e) {{ console.warn(tag, "apply err", e); }}
  }}

  // Strategy 1: patch parent's getUserMedia
  const win = window.parent;
  const patched = patchGetUserMedia(win);

  // Strategy 2: stop existing tracks → Streamlit re-requests with new (patched) constraints
  setTimeout(() => stopTracks(win), 50);

  // Strategy 3: also try applyConstraints on whatever's active (covers existing stream)
  setTimeout(() => applyToActive(win), 800);
  setTimeout(() => applyToActive(win), 2000);
}})();
</script>
""", height=0)

MAX_PHOTOS = 4

_PHOTO_CSS = """
<style>
/* 사진 그리드 높이 통일 */
[class*="st-key-photo_del_btn_"] ~ div [data-testid="stImage"] img,
[data-testid="stImage"] img {
    object-fit: cover !important;
}
.photo-grid-cell {
    display: flex;
    flex-direction: column;
    height: 100%;
}

[data-testid="stCameraInput"] video,
[data-testid="stCameraInput"] canvas,
[data-testid="stCameraInput"] img {
    max-width: 720px !important;
    max-height: 540px !important;
    width: 100% !important;
}
[data-testid="stCameraInput"] > div { max-width: 720px !important; margin: 0 auto !important; }
[data-testid="stCameraInput"] [data-testid="stWidgetLabel"],
[data-testid="stCameraInput"] label {
    margin-bottom: 0 !important; padding-bottom: 0 !important; line-height: 1 !important;
}
[data-testid="stCameraInputWebcamComponent"] > div:first-child {
    max-height: 500px !important; overflow: hidden !important;
}
[class*="st-key-photo_del_btn_"] button {
    padding: 0 10px !important; min-height: unset !important; height: 28px !important;
    font-size: 12px !important; border-radius: 4px !important;
    background: #ef4444 !important; border-color: #ef4444 !important;
    color: #ffffff !important; display: inline-flex !important; align-items: center !important;
}
[class*="st-key-photo_del_btn_"] button p { font-size:12px !important; margin:0 !important; color:#ffffff !important; }
[class*="st-key-photo_del_btn_"] button:hover { background:#dc2626 !important; border-color:#dc2626 !important; }
</style>
"""


def ui_photo_upload(con: Client, rid: str):
    """사진 최대 4장 등록 (촬영 또는 파일 업로드)."""
    st.markdown(_PHOTO_CSS, unsafe_allow_html=True)

    existing = photos_for_req(con, rid)
    count = len(existing)

    # ── 등록된 사진 목록 ──────────────────────────────────────────────────
    if existing:
        st.markdown(f"**등록된 사진 ({count}/{MAX_PHOTOS})**")

        # 2열 그리드 — 사진 + 파일명 + 삭제 버튼을 셀 단위로 묶어서 렌더링
        for row_start in range(0, len(existing), 2):
            row_photos = existing[row_start:row_start + 2]
            cols = st.columns(2)
            for col, p in zip(cols, row_photos):
                with col:
                    src = p.get("storage_url") or ""
                    if not src:
                        legacy = p.get("file_path") or ""
                        if legacy and Path(legacy).exists():
                            src = str(legacy)
                    if src:
                        st.image(src, use_container_width=True)
                    else:
                        st.markdown(
                            '<div style="height:160px;background:#f1f5f9;border-radius:6px;'
                            'display:flex;align-items:center;justify-content:center;'
                            'color:#94a3b8;font-size:12px;">파일 없음</div>',
                            unsafe_allow_html=True,
                        )
                    label = p.get('label', '')
                    st.markdown(
                        f'<p style="font-size:11px;color:#64748b;margin:2px 0 4px;'
                        f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{label}</p>',
                        unsafe_allow_html=True,
                    )
                    with st.container(key=f"photo_del_btn_{p['id'][:8]}"):
                        if st.button("삭제", key=f"photo_del_{p['id'][:8]}", use_container_width=False):
                            photo_delete_slot(con, rid, p.get("slot_key", ""))
                            st.rerun()

        st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)

    # ── 추가 업로드 (4장 미만일 때만) ────────────────────────────────────
    if count < MAX_PHOTOS:
        remaining = MAX_PHOTOS - count
        st.markdown(f"**사진 추가** (현재 {count}장 · 최대 {remaining}장 더 추가 가능)")
        mode = st.radio("입력 방식", ["직접 촬영", "파일 업로드"], horizontal=True,
                        key=f"photo_mode_{rid}", label_visibility="collapsed")
        if mode == "직접 촬영":
            facing = _camera_facing_toggle(rid)
            # key에 facing 포함 → 전환 시 카메라 새로 초기화 (권한 재요청 가능)
            pic = st.camera_input(
                "카메라로 촬영",
                key=f"photo_camera_{rid}_{count}_{facing}",
            )
            # active video track에 facingMode 적용 (best-effort)
            _inject_camera_facing_js(facing)
            if pic:
                data = bytes_from_camera_or_upload(pic)
                if data:
                    photo_add(con, rid, f"photo_{count + 1}", f"사진 {count + 1}", data, ".jpg")
                    st.rerun()
        else:
            uploads = st.file_uploader(
                f"사진 선택 (최대 {remaining}장, 복수 선택 가능)",
                type=["jpg", "jpeg", "png"],
                accept_multiple_files=True,
                key=f"photo_upload_{rid}_{count}",
            )
            if uploads:
                saved = 0
                for i, upl in enumerate(uploads[:remaining]):
                    data = bytes_from_camera_or_upload(upl)
                    if data:
                        photo_add(con, rid, f"photo_{count + i + 1}", upl.name, data, ".jpg")
                        saved += 1
                if saved:
                    st.rerun()
    else:
        st.info(f"사진 {MAX_PHOTOS}장이 모두 등록되었습니다. 삭제 후 다시 추가할 수 있습니다.")


# 하위 호환성 유지
def ui_photo_capture_required(con: Client, rid: str):
    ui_photo_upload(con, rid)


def ui_photo_optional_upload(con: Client, rid: str):
    pass
