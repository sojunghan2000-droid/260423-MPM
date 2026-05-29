"""PWA (Progressive Web App) manifest + Apple meta 주입.

Streamlit 기본 `/manifest.json` 은 `name: "Streamlit"` 으로 고정되어 있어
설치 시 PWA 라벨이 "Streamlit" 으로 표시됨. 본 모듈은 parent window 의
<head> 에 데이터 URI 기반 커스텀 manifest 와 Apple iOS 메타태그를 주입해
앱 명칭과 아이콘을 송도2-INO 로 덮어쓴다.

Streamlit 의 `[server] enableStaticServing = true` 옵션이 활성화되어
있어야 하며, 아이콘 파일은 project_root/static/icon-{192,512,180}.png
에 존재해야 함.

사용:
    from core.pwa import inject_pwa
    inject_pwa()   # app.py main() 의 첫 부분에서 호출
"""
from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components


APP_NAME       = "송도2-INO"
APP_SHORT_NAME = "송도2"
APP_DESCRIPTION = "송도역세권 2BL 자재 반출입 관리"
THEME_COLOR     = "#1d4ed8"
BG_COLOR        = "#f8fafc"

# Streamlit 의 정적 서빙 경로. Cloud / localhost 모두 동일 URL 규칙.
_ICON_192 = "./app/static/icon-192.png"
_ICON_512 = "./app/static/icon-512.png"
_ICON_180 = "./app/static/icon-180.png"


def _build_manifest_data_uri() -> str:
    manifest = {
        "name":             APP_NAME,
        "short_name":       APP_SHORT_NAME,
        "description":      APP_DESCRIPTION,
        "start_url":        ".",
        "scope":            ".",
        "display":          "standalone",
        "orientation":      "any",
        "theme_color":      THEME_COLOR,
        "background_color": BG_COLOR,
        "lang":             "ko",
        "icons": [
            {"src": _ICON_192, "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": _ICON_512, "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ],
    }
    raw = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
    # 안전한 인코딩 — JS 에 그대로 넣지 않고 base64 데이터 URI 로 노출
    import base64
    b64 = base64.b64encode(raw.encode("utf-8")).decode("ascii")
    return f"data:application/manifest+json;base64,{b64}"


def inject_pwa() -> None:
    """parent window <head> 에 커스텀 manifest + Apple 메타 + 타이틀 주입.

    세션당 1회만 실행. iframe 안에서 parent.document 를 수정한다.
    """
    if st.session_state.get("__pwa_injected"):
        return
    st.session_state["__pwa_injected"] = True

    manifest_uri = _build_manifest_data_uri()

    components.html(
        f"""
        <script>
        (function() {{
          try {{
            const pdoc = window.parent.document;
            const OUR_MANIFEST = {json.dumps(manifest_uri)};
            const OUR_TOUCH_ICON = {json.dumps(_ICON_180)};
            const OUR_TITLE = {json.dumps(APP_NAME)};
            const OUR_SHORT = {json.dumps(APP_SHORT_NAME)};
            const OUR_THEME = {json.dumps(THEME_COLOR)};

            function applyOverrides() {{
              // 1) 우리 것이 아닌 manifest <link> 제거 + 우리 것 보장
              let ourMl = null;
              pdoc.querySelectorAll('link[rel="manifest"]').forEach(el => {{
                if (el.href === OUR_MANIFEST) ourMl = el;
                else el.remove();
              }});
              if (!ourMl) {{
                ourMl = pdoc.createElement('link');
                ourMl.rel = 'manifest';
                ourMl.href = OUR_MANIFEST;
                pdoc.head.appendChild(ourMl);
              }}

              // 2) Apple iOS 메타
              const setMeta = (sel, attrs) => {{
                let el = pdoc.head.querySelector(sel);
                if (!el) {{
                  el = pdoc.createElement(sel.split('[')[0]);
                  pdoc.head.appendChild(el);
                }}
                for (const k in attrs) el.setAttribute(k, attrs[k]);
              }};
              setMeta('meta[name="apple-mobile-web-app-title"]',
                      {{name: 'apple-mobile-web-app-title', content: OUR_SHORT}});
              setMeta('meta[name="apple-mobile-web-app-capable"]',
                      {{name: 'apple-mobile-web-app-capable', content: 'yes'}});
              setMeta('meta[name="apple-mobile-web-app-status-bar-style"]',
                      {{name: 'apple-mobile-web-app-status-bar-style', content: 'default'}});
              setMeta('meta[name="theme-color"]',
                      {{name: 'theme-color', content: OUR_THEME}});

              // 3) apple-touch-icon — 우리 것 아닌 건 제거
              let ourAi = null;
              pdoc.querySelectorAll('link[rel="apple-touch-icon"]').forEach(el => {{
                if (el.getAttribute('href') === OUR_TOUCH_ICON) ourAi = el;
                else el.remove();
              }});
              if (!ourAi) {{
                ourAi = pdoc.createElement('link');
                ourAi.rel = 'apple-touch-icon';
                ourAi.href = OUR_TOUCH_ICON;
                pdoc.head.appendChild(ourAi);
              }}

              // 4) 페이지 타이틀이 "Streamlit" 으로 떨어지면 보정
              if (pdoc.title === 'Streamlit' || !pdoc.title) {{
                pdoc.title = OUR_TITLE;
              }}
            }}

            applyOverrides();

            // ── 방어 1: <head> 변경 감지해 Streamlit 이 기본 manifest 를 재삽입하면 즉시 제거 ──
            if (!pdoc.__pwaHeadObserver) {{
              const obs = new MutationObserver(applyOverrides);
              obs.observe(pdoc.head, {{ childList: true, subtree: true }});
              pdoc.__pwaHeadObserver = obs;
            }}

            // ── 방어 2: 첫 5초 동안 0.5초 간격 재적용 (지연 로딩 대비) ──
            let attempts = 0;
            const iv = setInterval(() => {{
              applyOverrides();
              if (++attempts >= 10) clearInterval(iv);
            }}, 500);

            console.log('[pwa] manifest+apple meta injected:', OUR_TITLE);
          }} catch (e) {{
            console.warn('[pwa] inject failed:', e);
          }}
        }})();
        </script>
        """,
        height=0,
    )
