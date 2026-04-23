const pptxgen = require("pptxgenjs");
const path = require("path");

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.title = "자재 반출입 관리 시스템 UI 설명";

const NAVY   = "1E3A8A";
const BLUE   = "2563EB";
const LBLUE  = "DBEAFE";
const ORANGE = "F97316";
const WHITE  = "FFFFFF";
const DARK   = "1E293B";
const MUTED  = "64748B";
const BGLT   = "F0F4FF";
const GREEN  = "059669";
const TEAL   = "0891B2";
const PURPLE = "7C3AED";

const IMG = (name) => path.join(__dirname, "ppt_screens", `${name}.png`);

// ── 슬라이드 공통 헬퍼 ─────────────────────────────────────────────────────
function addHeader(slide, title, icon = "") {
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.65,
    fill: { color: NAVY }, line: { color: NAVY }
  });
  slide.addText(`${icon}  ${title}`, {
    x: 0.3, y: 0, w: 9.4, h: 0.65,
    fontSize: 20, bold: true, color: WHITE, valign: "middle", margin: 0
  });
}

function addScreenshot(slide, imgFile, x, y, w, h) {
  // shadow box behind image
  slide.addShape(pres.shapes.RECTANGLE, {
    x: x + 0.05, y: y + 0.05, w, h,
    fill: { color: "000000", transparency: 85 },
    line: { color: "000000", transparency: 85 }
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h,
    fill: { color: "E2E8F0" }, line: { color: "CBD5E1", width: 1 }
  });
  slide.addImage({ path: imgFile, x, y, w, h, sizing: { type: "contain", w, h } });
}

function addBullets(slide, items, x, y, w, h, opts = {}) {
  const rows = items.map((item, i) => ({
    text: item.text,
    options: { bullet: item.bullet !== false, breakLine: i < items.length - 1, ...item.opts }
  }));
  slide.addText(rows, {
    x, y, w, h,
    fontSize: opts.fontSize || 13,
    color: opts.color || DARK,
    fontFace: "Calibri",
    lineSpacingMultiple: 1.3,
    ...opts
  });
}

function addTag(slide, text, x, y, color, bg) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w: 1.1, h: 0.28,
    fill: { color: bg }, line: { color: color }, rectRadius: 0.05
  });
  slide.addText(text, {
    x, y, w: 1.1, h: 0.28,
    fontSize: 9, bold: true, color: color,
    align: "center", valign: "middle", margin: 0
  });
}

// ══════════════════════════════════════════════════════════════════════════════
// 슬라이드 1 — 타이틀
// ══════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: NAVY };

  // 배경 그래픽 요소
  slide_shapes: {
    s.addShape(pres.shapes.OVAL, {
      x: 7.5, y: -1.5, w: 5, h: 5,
      fill: { color: "2563EB", transparency: 75 }, line: { color: "2563EB", transparency: 75 }
    });
    s.addShape(pres.shapes.OVAL, {
      x: -1, y: 3, w: 4, h: 4,
      fill: { color: "1D4ED8", transparency: 80 }, line: { color: "1D4ED8", transparency: 80 }
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0, y: 4.8, w: 10, h: 0.825,
      fill: { color: "F97316", transparency: 0 }, line: { color: "F97316" }
    });
  }

  s.addText("🏗️", { x: 1, y: 0.6, w: 1, h: 1, fontSize: 42, align: "center" });

  s.addText("자재 반출입 관리 시스템", {
    x: 0.8, y: 1.5, w: 8.4, h: 0.9,
    fontSize: 38, bold: true, color: WHITE, align: "center", fontFace: "Calibri"
  });

  s.addText("Material Gate Tool  v3.0.0", {
    x: 0.8, y: 2.4, w: 8.4, h: 0.5,
    fontSize: 16, color: LBLUE, align: "center", fontFace: "Calibri"
  });

  s.addText("UI 화면 설명 자료", {
    x: 0.8, y: 3.0, w: 8.4, h: 0.5,
    fontSize: 14, color: "94A3B8", align: "center", fontFace: "Calibri"
  });

  s.addText("건설현장 자재 반출입 승인 · 실행 · 산출물 관리 통합 플랫폼", {
    x: 0, y: 4.8, w: 10, h: 0.825,
    fontSize: 13, color: WHITE, align: "center", valign: "middle", bold: false, margin: 0
  });
}

// ══════════════════════════════════════════════════════════════════════════════
// 슬라이드 2 — 시스템 워크플로우
// ══════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: BGLT };
  addHeader(s, "시스템 워크플로우", "🔄");

  s.addText("자재 반출입 처리 전 과정을 디지털로 관리합니다", {
    x: 1, y: 0.75, w: 8, h: 0.4,
    fontSize: 13, color: MUTED, align: "center"
  });

  const steps = [
    { icon: "📅", title: "계획", sub: "타임라인 슬롯 선택\n예약 신청", color: BLUE, bg: "DBEAFE" },
    { icon: "✍️", title: "승인", sub: "안전·공사 담당자\n서명 승인", color: GREEN, bg: "DCFCE7" },
    { icon: "📸", title: "확인", sub: "현장 사진 촬영\n체크리스트", color: ORANGE, bg: "FFEDD5" },
    { icon: "📦", title: "산출물", sub: "PDF 생성\n카카오 공유", color: PURPLE, bg: "EDE9FE" },
    { icon: "📋", title: "대장", sub: "전체 이력\n검색·조회", color: TEAL, bg: "CFFAFE" },
  ];

  const boxW = 1.55, boxH = 2.8, startX = 0.3, y = 1.3, gap = 0.12;

  steps.forEach((step, i) => {
    const x = startX + i * (boxW + gap);

    // 카드 배경
    s.addShape(pres.shapes.RECTANGLE, {
      x, y, w: boxW, h: boxH,
      fill: { color: step.bg }, line: { color: step.color, width: 1.5 },
      shadow: { type: "outer", color: "000000", blur: 8, offset: 2, angle: 135, opacity: 0.1 }
    });

    // 번호 원
    s.addShape(pres.shapes.OVAL, {
      x: x + boxW / 2 - 0.22, y: y + 0.12,
      w: 0.44, h: 0.44,
      fill: { color: step.color }, line: { color: step.color }
    });
    s.addText(`${i + 1}`, {
      x: x + boxW / 2 - 0.22, y: y + 0.12,
      w: 0.44, h: 0.44,
      fontSize: 13, bold: true, color: WHITE, align: "center", valign: "middle", margin: 0
    });

    // 아이콘
    s.addText(step.icon, {
      x, y: y + 0.64, w: boxW, h: 0.6,
      fontSize: 26, align: "center", margin: 0
    });

    // 제목
    s.addText(step.title, {
      x, y: y + 1.3, w: boxW, h: 0.4,
      fontSize: 15, bold: true, color: step.color, align: "center", margin: 0
    });

    // 설명
    s.addText(step.sub, {
      x: x + 0.08, y: y + 1.75, w: boxW - 0.16, h: 0.9,
      fontSize: 10.5, color: DARK, align: "center", margin: 0
    });

    // 화살표
    if (i < steps.length - 1) {
      s.addShape(pres.shapes.LINE, {
        x: x + boxW + 0.01, y: y + boxH / 2,
        w: gap + 0.01, h: 0,
        line: { color: NAVY, width: 1.8, dashType: "solid" }
      });
      s.addText("▶", {
        x: x + boxW + gap - 0.1, y: y + boxH / 2 - 0.15,
        w: 0.2, h: 0.3,
        fontSize: 9, color: NAVY, margin: 0
      });
    }
  });

  s.addText("사용자 역할: 협력사(신청) · 공사/안전(승인) · 경비(확인) · 관리자(전체)", {
    x: 0.5, y: 4.9, w: 9, h: 0.4,
    fontSize: 11, color: MUTED, align: "center",
    italic: true
  });
}

// ══════════════════════════════════════════════════════════════════════════════
// 슬라이드 3 — 프로젝트 선택 & 로그인
// ══════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  addHeader(s, "프로젝트 선택 & 로그인", "🔐");

  // 왼쪽: 프로젝트 선택
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.3, y: 0.75, w: 4.3, h: 0.35,
    fill: { color: LBLUE }, line: { color: BLUE, width: 0.5 }
  });
  s.addText("① 프로젝트 선택", {
    x: 0.3, y: 0.75, w: 4.3, h: 0.35,
    fontSize: 12, bold: true, color: BLUE, valign: "middle", margin: 8
  });
  addScreenshot(s, IMG("01_project_select"), 0.3, 1.15, 4.3, 2.7);

  addBullets(s, [
    { text: "현장 프로젝트 드롭다운 선택", opts: { bullet: { color: BLUE } } },
    { text: "▶ 버튼 또는 Enter로 진입" },
    { text: "+ 새 프로젝트 만들기 (현장명, PIN 설정)" },
  ], 0.3, 3.95, 4.3, 1.2, { fontSize: 11, color: DARK });

  // 오른쪽: 로그인
  s.addShape(pres.shapes.RECTANGLE, {
    x: 5.0, y: 0.75, w: 4.6, h: 0.35,
    fill: { color: LBLUE }, line: { color: BLUE, width: 0.5 }
  });
  s.addText("② 로그인 / 회원가입", {
    x: 5.0, y: 0.75, w: 4.6, h: 0.35,
    fontSize: 12, bold: true, color: BLUE, valign: "middle", margin: 8
  });
  addScreenshot(s, IMG("02_login"), 5.0, 1.15, 4.6, 2.7);

  addBullets(s, [
    { text: "아이디 + 비밀번호 로그인" },
    { text: "회원가입: 아이디·이름·부서 선택" },
    { text: "Admin PIN 입력 시 관리자 권한 부여" },
    { text: "역할: 협력사 / 공사 / 안전 / 경비" },
  ], 5.0, 3.95, 4.6, 1.2, { fontSize: 11, color: DARK });
}

// ══════════════════════════════════════════════════════════════════════════════
// 슬라이드 4 — 홈 화면
// ══════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  addHeader(s, "🏠  홈 화면 — 대시보드", "");

  addScreenshot(s, IMG("04_home"), 0.3, 0.75, 5.8, 4.4);

  // 오른쪽 설명
  s.addText("주요 기능", {
    x: 6.4, y: 0.85, w: 3.3, h: 0.35,
    fontSize: 13, bold: true, color: NAVY
  });

  const features = [
    { icon: "📊", text: "프로젝트 현황 카드\n전체/대기/승인/완료 건수 한눈에 파악" },
    { icon: "🧭", text: "상단 탭 네비게이션\n계획·승인·확인·산출물·대장 이동" },
    { icon: "📋", text: "진행 중인 요청 목록\n상태 아이콘 + 클릭 시 해당 탭 이동" },
    { icon: "➕", text: "신규 신청 버튼\n계획 탭으로 바로 이동" },
    { icon: "🗑️", text: "삭제 기능\n관리자: 전체 / 협력사: 본인 요청만" },
  ];

  features.forEach((f, i) => {
    const y = 1.3 + i * 0.75;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 6.4, y, w: 3.3, h: 0.62,
      fill: { color: BGLT }, line: { color: LBLUE, width: 0.5 }
    });
    s.addText(f.icon, { x: 6.5, y: y + 0.05, w: 0.4, h: 0.5, fontSize: 14, margin: 0 });
    s.addText(f.text, {
      x: 6.95, y: y + 0.04, w: 2.65, h: 0.55,
      fontSize: 10, color: DARK, margin: 0
    });
  });
}

// ══════════════════════════════════════════════════════════════════════════════
// 슬라이드 5 — 계획 화면
// ══════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  addHeader(s, "📅  계획 — 타임라인 & 예약 신청", "");

  addScreenshot(s, IMG("05_schedule"), 0.3, 0.75, 5.8, 4.4);

  s.addText("주요 기능", { x: 6.4, y: 0.85, w: 3.3, h: 0.35, fontSize: 13, bold: true, color: NAVY });

  const items = [
    { icon: "🕐", text: "30분 단위 타임라인\n반입(파란색) / 반출(빨간색) 레인 구분" },
    { icon: "🖱️", text: "슬롯 클릭으로 시간 선택\n선택된 슬롯 자동으로 예약 폼에 반영" },
    { icon: "📝", text: "예약 신청 폼\n협력사명·자재명·차량·운전원 입력" },
    { icon: "📅", text: "날짜 네비게이션\n오늘 기준 ±2일 조회 및 이동" },
    { icon: "🔀", text: "관리자 드래그&드롭\n기존 예약 슬롯 이동·수정·삭제" },
  ];

  items.forEach((f, i) => {
    const y = 1.3 + i * 0.75;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 6.4, y, w: 3.3, h: 0.62,
      fill: { color: BGLT }, line: { color: LBLUE, width: 0.5 }
    });
    s.addText(f.icon, { x: 6.5, y: y + 0.05, w: 0.4, h: 0.5, fontSize: 14, margin: 0 });
    s.addText(f.text, { x: 6.95, y: y + 0.04, w: 2.65, h: 0.55, fontSize: 10, color: DARK, margin: 0 });
  });
}

// ══════════════════════════════════════════════════════════════════════════════
// 슬라이드 6 — 승인 화면
// ══════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  addHeader(s, "✍️  승인 — 서명 기반 승인 처리", "");

  addScreenshot(s, IMG("06_approval"), 0.3, 0.75, 5.8, 4.4);

  s.addText("주요 기능", { x: 6.4, y: 0.85, w: 3.3, h: 0.35, fontSize: 13, bold: true, color: NAVY });

  const items = [
    { icon: "📋", text: "내 승인함\n역할에 따라 해당 건만 표시" },
    { icon: "✏️", text: "서명 패드\n터치/마우스로 직접 서명 입력" },
    { icon: "✅", text: "승인 / 반려 처리\n반려 시 사유 입력 필수" },
    { icon: "🔀", text: "승인 라우팅 설정\n반입: 공사 / 반출: 안전+공사 (설정 가능)" },
    { icon: "🔔", text: "상태 자동 전환\n승인 완료 시 → APPROVED 상태 변경" },
  ];

  items.forEach((f, i) => {
    const y = 1.3 + i * 0.75;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 6.4, y, w: 3.3, h: 0.62,
      fill: { color: BGLT }, line: { color: LBLUE, width: 0.5 }
    });
    s.addText(f.icon, { x: 6.5, y: y + 0.05, w: 0.4, h: 0.5, fontSize: 14, margin: 0 });
    s.addText(f.text, { x: 6.95, y: y + 0.04, w: 2.65, h: 0.55, fontSize: 10, color: DARK, margin: 0 });
  });
}

// ══════════════════════════════════════════════════════════════════════════════
// 슬라이드 7 — 확인 화면
// ══════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  addHeader(s, "📸  확인 — 사진 촬영 & 체크리스트", "");

  addScreenshot(s, IMG("07_execution"), 0.3, 0.75, 5.8, 4.4);

  s.addText("주요 기능", { x: 6.4, y: 0.85, w: 3.3, h: 0.35, fontSize: 13, bold: true, color: NAVY });

  const items = [
    { icon: "📷", text: "필수 사진 3종\n상차 전·후, 현장 통제 구역 직접 촬영" },
    { icon: "🔁", text: "사진 변경 기능\n등록된 사진을 나중에 교체 가능" },
    { icon: "☑️", text: "자재 상·하차 점검카드\n체크리스트 항목 확인 및 체크" },
    { icon: "📝", text: "메모 입력\n현장 특이사항 자유 기재" },
    { icon: "🔒", text: "등록 완료 후 잠금\n재등록 버튼으로 수정 가능" },
  ];

  items.forEach((f, i) => {
    const y = 1.3 + i * 0.75;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 6.4, y, w: 3.3, h: 0.62,
      fill: { color: BGLT }, line: { color: LBLUE, width: 0.5 }
    });
    s.addText(f.icon, { x: 6.5, y: y + 0.05, w: 0.4, h: 0.5, fontSize: 14, margin: 0 });
    s.addText(f.text, { x: 6.95, y: y + 0.04, w: 2.65, h: 0.55, fontSize: 10, color: DARK, margin: 0 });
  });
}

// ══════════════════════════════════════════════════════════════════════════════
// 슬라이드 8 — 산출물 & 대장
// ══════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  addHeader(s, "📦 산출물 & 📋 대장", "");

  // 산출물 (왼쪽)
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.3, y: 0.75, w: 4.3, h: 0.32,
    fill: { color: "EDE9FE" }, line: { color: PURPLE, width: 0.5 }
  });
  s.addText("📦 산출물 — PDF 생성 & 공유", {
    x: 0.3, y: 0.75, w: 4.3, h: 0.32,
    fontSize: 11, bold: true, color: PURPLE, valign: "middle", margin: 6
  });
  addScreenshot(s, IMG("08_outputs"), 0.3, 1.12, 4.3, 2.6);

  addBullets(s, [
    { text: "계획서 · 허가서 · 실행요약 PDF 자동 생성" },
    { text: "카카오톡 공유 링크 생성 (QR코드 포함)" },
    { text: "PDF 다운로드 및 재생성" },
  ], 0.3, 3.8, 4.3, 1.3, { fontSize: 10.5, color: DARK });

  // 대장 (오른쪽)
  s.addShape(pres.shapes.RECTANGLE, {
    x: 5.0, y: 0.75, w: 4.6, h: 0.32,
    fill: { color: "CFFAFE" }, line: { color: TEAL, width: 0.5 }
  });
  s.addText("📋 대장 — 전체 이력 조회", {
    x: 5.0, y: 0.75, w: 4.6, h: 0.32,
    fontSize: 11, bold: true, color: TEAL, valign: "middle", margin: 6
  });
  addScreenshot(s, IMG("09_ledger"), 5.0, 1.12, 4.6, 2.6);

  addBullets(s, [
    { text: "구분(반입/반출) · 상태 필터링" },
    { text: "키워드 검색 (회사명, 자재명, 운전원)" },
    { text: "관리자: 대장에서 직접 삭제 가능" },
  ], 5.0, 3.8, 4.6, 1.3, { fontSize: 10.5, color: DARK });
}

// ══════════════════════════════════════════════════════════════════════════════
// 슬라이드 9 — 관리자 설정
// ══════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  addHeader(s, "⚙️  관리자 설정", "");

  addScreenshot(s, IMG("10_admin"), 0.3, 0.75, 5.8, 4.4);

  s.addText("주요 기능", { x: 6.4, y: 0.85, w: 3.3, h: 0.35, fontSize: 13, bold: true, color: NAVY });

  const items = [
    { icon: "🏗️", text: "현장 설정\n현장명 / 현장 PIN / Admin PIN 변경" },
    { icon: "🔀", text: "승인 라우팅 설정\n반입·반출별 승인 담당 역할 지정" },
    { icon: "🧩", text: "모듈 활성화 관리\n사용할 탭(계획·승인·확인 등) 켜기/끄기" },
    { icon: "👥", text: "계정 관리\n등록된 사용자 목록 조회 및 삭제" },
    { icon: "📊", text: "접근 제한\n관리자 PIN을 가진 사용자만 접근 가능" },
  ];

  items.forEach((f, i) => {
    const y = 1.3 + i * 0.75;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 6.4, y, w: 3.3, h: 0.62,
      fill: { color: BGLT }, line: { color: LBLUE, width: 0.5 }
    });
    s.addText(f.icon, { x: 6.5, y: y + 0.05, w: 0.4, h: 0.5, fontSize: 14, margin: 0 });
    s.addText(f.text, { x: 6.95, y: y + 0.04, w: 2.65, h: 0.55, fontSize: 10, color: DARK, margin: 0 });
  });
}

// ══════════════════════════════════════════════════════════════════════════════
// 슬라이드 10 — 모바일 & 마무리
// ══════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: NAVY };

  s.addShape(pres.shapes.OVAL, {
    x: 7, y: -1, w: 5, h: 5,
    fill: { color: "2563EB", transparency: 75 }, line: { color: "2563EB", transparency: 75 }
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 4.8, w: 10, h: 0.825,
    fill: { color: ORANGE }, line: { color: ORANGE }
  });

  s.addText("모바일 반응형 설계", {
    x: 0.8, y: 0.7, w: 8.4, h: 0.6,
    fontSize: 28, bold: true, color: WHITE, align: "center"
  });

  const points = [
    { icon: "📱", title: "스마트폰 최적화", desc: "현장 작업자(경비·협력사) 한 손 조작 고려\n버튼 최소 높이 44px (iOS HIG 기준)" },
    { icon: "💻", title: "태블릿·데스크톱", desc: "공사·안전 담당자 서명 입력\n관리자 데이터 테이블·필터 사용" },
    { icon: "⚡", title: "실시간 처리", desc: "상태 변경 즉시 반영\nPDF 자동 생성 및 카카오 공유" },
  ];

  points.forEach((p, i) => {
    const x = 0.5 + i * 3.1;
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.5, w: 2.8, h: 2.9,
      fill: { color: "1D4ED8", transparency: 30 }, line: { color: "3B82F6", width: 1 }
    });
    s.addText(p.icon, { x, y: 1.65, w: 2.8, h: 0.6, fontSize: 28, align: "center", margin: 0 });
    s.addText(p.title, {
      x, y: 2.3, w: 2.8, h: 0.4,
      fontSize: 13, bold: true, color: WHITE, align: "center", margin: 0
    });
    s.addText(p.desc, {
      x: x + 0.1, y: 2.75, w: 2.6, h: 1.5,
      fontSize: 10.5, color: LBLUE, align: "center", margin: 0
    });
  });

  s.addText("자재 반출입 관리 시스템  ·  Material Gate Tool v3.0.0", {
    x: 0, y: 4.8, w: 10, h: 0.825,
    fontSize: 12, color: WHITE, align: "center", valign: "middle", margin: 0
  });
}

// ── 저장 ───────────────────────────────────────────────────────────────────
const outPath = "C:/Users/user/Desktop/자재반출입관리_시스템_UI설명.pptx";
pres.writeFile({ fileName: outPath }).then(() => {
  console.log("✅ PPT 저장 완료:", outPath);
}).catch(err => {
  console.error("❌ 오류:", err);
});
