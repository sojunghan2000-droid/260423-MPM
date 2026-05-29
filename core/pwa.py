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

            // 1) 기존 Streamlit manifest <link> 제거
            pdoc.querySelectorAll('link[rel="manifest"]').forEach(el => el.remove());

            // 2) 새 manifest 주입
            const ml = pdoc.createElement('link');
            ml.rel = 'manifest';
            ml.href = {json.dumps(manifest_uri)};
            pdoc.head.appendChild(ml);

            // 3) Apple iOS — manifest 무시하므로 메타태그로 별도 지정
            const setMeta = (sel, attrs) => {{
              let el = pdoc.head.querySelector(sel);
              if (!el) {{
                el = pdoc.createElement(sel.split('[')[0]);
                pdoc.head.appendChild(el);
              }}
              for (const k in attrs) el.setAttribute(k, attrs[k]);
            }};
            setMeta('meta[name="apple-mobile-web-app-title"]',
                    {{name: 'apple-mobile-web-app-title', content: {json.dumps(APP_SHORT_NAME)}}});
            setMeta('meta[name="apple-mobile-web-app-capable"]',
                    {{name: 'apple-mobile-web-app-capable', content: 'yes'}});
            setMeta('meta[name="apple-mobile-web-app-status-bar-style"]',
                    {{name: 'apple-mobile-web-app-status-bar-style', content: 'default'}});

            // Apple touch icon (180x180)
            pdoc.querySelectorAll('link[rel="apple-touch-icon"]').forEach(el => el.remove());
            const ai = pdoc.createElement('link');
            ai.rel = 'apple-touch-icon';
            ai.href = {json.dumps(_ICON_180)};
            pdoc.head.appendChild(ai);

            // theme-color 메타도 동기화
            setMeta('meta[name="theme-color"]',
                    {{name: 'theme-color', content: {json.dumps(THEME_COLOR)}}});

            // 4) 페이지 타이틀 (st.set_page_config 가 set 한 값을 덮어쓰지 않음)
            //    Streamlit 기본 타이틀이 "Streamlit" 으로 떨어지는 경우만 보정
            if (pdoc.title === 'Streamlit' || !pdoc.title) {{
              pdoc.title = {json.dumps(APP_NAME)};
            }}

            console.log('[pwa] manifest+apple meta injected:', {json.dumps(APP_NAME)});
          }} catch (e) {{
            console.warn('[pwa] inject failed:', e);
          }}
        }})();
        </script>
        """,
        height=0,
    )
