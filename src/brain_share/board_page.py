"""Single-page HTML for the local task board (served at /board).

Vanilla JS, no external assets — the hub may be offline. Talks only to
/api/tasks* on the same origin with the X-Brain-Board-Key header; the key is
kept in sessionStorage (gone when the tab closes). Every server string goes
through esc() before it touches innerHTML.
"""

BOARD_HTML = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>업무 보드 — Mokai Brain Kit</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%F0%9F%A7%A0%3C/text%3E%3C/svg%3E">
<style>
  :root {
    color-scheme: dark;
    --bg: #0f172a; --panel: #1e293b; --panel-2: #172033; --line: #334155;
    --text: #e2e8f0; --muted: #94a3b8; --faint: #64748b; --accent: #38bdf8;
    --ok: #4ade80; --warn: #fbbf24; --bad: #f87171; --violet: #a78bfa;
  }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Malgun Gothic", system-ui, sans-serif;
         margin: 0; padding: 20px 24px 40px; background: var(--bg); color: var(--text); }
  a { color: var(--accent); }
  header { display: flex; align-items: center; gap: 20px; flex-wrap: wrap; margin-bottom: 16px; }
  h1 { margin: 0; font-size: 20px; }
  nav { display: flex; gap: 4px; }
  nav a { padding: 6px 12px; border-radius: 8px; text-decoration: none; color: var(--muted); font-size: 14px; }
  nav a:hover { background: var(--panel); color: var(--text); }
  nav a.on { background: var(--panel); color: var(--text); border: 1px solid var(--line); }
  button, .btn { font: inherit; font-size: 14px; border-radius: 8px; border: 1px solid var(--line);
                 background: var(--panel); color: var(--text); padding: 7px 14px; cursor: pointer;
                 white-space: nowrap; }
  .card { white-space: normal; }
  button:hover { border-color: var(--accent); }
  button:disabled { opacity: .5; cursor: default; }
  button.primary { background: #0369a1; border-color: #0284c7; }
  button.ok { background: #166534; border-color: #16a34a; }
  button.bad { background: #7f1d1d; border-color: #b91c1c; }
  button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible, .card:focus-visible {
    outline: 2px solid var(--accent); outline-offset: 2px; }
  input, select, textarea { font: inherit; font-size: 14px; color: var(--text); background: var(--panel-2);
                            border: 1px solid var(--line); border-radius: 8px; padding: 7px 10px; width: 100%; }
  textarea { min-height: 70px; resize: vertical; }
  label { display: block; font-size: 12px; color: var(--muted); margin: 10px 0 4px; }
  .toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 14px; }
  .toolbar .spacer { flex: 1; }
  .chip { border-radius: 999px; padding: 5px 12px; font-size: 13px; }
  .chip.on { background: #0c4a6e; border-color: var(--accent); }
  .chip .n { display: inline-block; min-width: 18px; margin-left: 4px; padding: 0 5px; border-radius: 9px;
             background: var(--line); font-size: 12px; text-align: center; }
  .chip.alert .n { background: var(--warn); color: #111; }
  .meta-line { color: var(--faint); font-size: 12px; }
  .cols { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; align-items: start; }
  @media (max-width: 1100px) { .cols { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  @media (max-width: 640px) {
    body { padding: 14px 16px 32px; }
    .cols { grid-template-columns: 1fr; }
  }
  .col { background: var(--panel-2); border: 1px solid var(--line); border-radius: 12px; padding: 12px; min-height: 120px; }
  .col.hl { border-color: var(--warn); box-shadow: 0 0 0 1px var(--warn) inset; }
  .col h2 { margin: 0 0 10px; font-size: 14px; display: flex; justify-content: space-between; color: var(--muted); }
  .col h2 .n { color: var(--text); }
  .empty { color: var(--faint); font-size: 13px; padding: 10px 2px; }
  .card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px;
          margin-bottom: 8px; cursor: pointer; display: block; width: 100%; text-align: left; }
  .card:hover { border-color: var(--accent); }
  .card.dim { opacity: .55; }
  .card .t { font-size: 14px; line-height: 1.4; margin: 4px 0 6px; word-break: break-word; }
  .card .m { display: flex; flex-wrap: wrap; gap: 6px 10px; font-size: 12px; color: var(--muted); }
  .badge { display: inline-block; font-size: 11px; padding: 1px 7px; border-radius: 6px; border: 1px solid var(--line); }
  .p-urgent { color: var(--bad); border-color: var(--bad); }
  .p-high { color: var(--warn); border-color: var(--warn); }
  .p-normal { color: var(--muted); }
  .p-low { color: var(--faint); }
  .s-blocked { color: var(--bad); border-color: var(--bad); }
  .s-review { color: var(--warn); border-color: var(--warn); }
  .s-done { color: var(--ok); border-color: var(--ok); }
  .s-in_progress { color: var(--accent); border-color: var(--accent); }
  .s-pending { color: var(--muted); }
  .late { color: var(--bad); }
  .gate { max-width: 420px; margin: 60px auto; background: var(--panel); border: 1px solid var(--line);
          border-radius: 12px; padding: 22px; }
  .gate h2 { margin: 0 0 6px; font-size: 17px; }
  .gate p { color: var(--muted); font-size: 13px; line-height: 1.6; margin: 0 0 8px; }
  .gate .row { display: flex; gap: 8px; align-items: center; }
  .gate .row input { flex: 1; min-width: 0; }
  .gate .row button { flex: none; white-space: nowrap; }
  .err { color: var(--bad); font-size: 13px; min-height: 18px; margin-top: 8px; }
  .notice { background: #3f1d1d; border: 1px solid #7f1d1d; color: #fecaca; border-radius: 10px; padding: 14px 16px;
            font-size: 14px; line-height: 1.6; max-width: 720px; }
  dialog { background: var(--panel); color: var(--text); border: 1px solid var(--line); border-radius: 14px;
           padding: 0; width: min(640px, calc(100vw - 32px)); max-height: calc(100vh - 48px); }
  dialog::backdrop { background: rgba(2, 6, 23, .7); }
  .dlg { padding: 18px 20px 20px; }
  .dlg-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
  .dlg-head h3 { margin: 0; font-size: 17px; line-height: 1.4; word-break: break-word; }
  .x { background: none; border: none; font-size: 22px; line-height: 1; padding: 2px 6px; color: var(--muted); }
  .grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 4px 16px; margin: 12px 0; }
  .kv .k { font-size: 12px; color: var(--muted); }
  .kv .v { font-size: 14px; word-break: break-word; }
  .sec { margin-top: 14px; }
  .sec h4 { margin: 0 0 6px; font-size: 13px; color: var(--muted); font-weight: 600; }
  .pre { white-space: pre-wrap; word-break: break-word; font-size: 14px; line-height: 1.55; }
  .hist { list-style: none; margin: 0; padding: 0; border-left: 2px solid var(--line); }
  .hist li { padding: 4px 0 8px 12px; font-size: 13px; }
  .hist .when { color: var(--faint); font-size: 12px; }
  .hist .what { color: var(--accent); }
  .actions { display: grid; gap: 10px; margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--line); }
  .act { display: flex; gap: 8px; align-items: flex-start; }
  .act > :first-child { flex: 1; }
  .act textarea { min-height: 44px; }
  .toast { position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%); background: var(--panel);
           border: 1px solid var(--line); border-radius: 10px; padding: 10px 16px; font-size: 14px;
           box-shadow: 0 6px 24px rgba(0,0,0,.4); z-index: 50; max-width: calc(100vw - 32px); }
  .toast.bad { border-color: var(--bad); color: #fecaca; }
  .toast.ok { border-color: var(--ok); }
  .hidden { display: none !important; }
  .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
</style>
</head>
<body>
<header>
  <h1>🧠 Mokai Brain Kit</h1>
  <nav aria-label="대시보드 메뉴">
    <a href="/">상태</a>
    <a href="/board" class="on" aria-current="page">업무 보드</a>
  </nav>
</header>

<div id="disabled" class="notice hidden" role="alert"></div>

<form id="gate" class="gate hidden" autocomplete="off">
  <h2>업무 보드 열기</h2>
  <p>보드 키를 입력하세요. 키는 이 탭에만 보관되고 탭을 닫으면 지워집니다.</p>
  <label for="gate-key">보드 키</label>
  <div class="row">
    <input id="gate-key" type="password" required autofocus>
    <button class="primary" type="submit">열기</button>
  </div>
  <div id="gate-err" class="err" role="alert"></div>
</form>

<main id="app" class="hidden">
  <div class="toolbar">
    <button id="btn-new" class="primary" type="button">＋ 새 업무</button>
    <button class="chip on" type="button" data-filter="all">전체 <span class="n" id="n-all">0</span></button>
    <button class="chip" type="button" data-filter="review">내 승인 대기 <span class="n" id="n-review">0</span></button>
    <button class="chip" type="button" data-filter="blocked">막힘 <span class="n" id="n-blocked">0</span></button>
    <button class="chip" type="button" data-filter="overdue">기한 지남 <span class="n" id="n-overdue">0</span></button>
    <span class="spacer"></span>
    <span class="meta-line" id="updated"></span>
    <button id="btn-refresh" type="button" title="새로고침">↻ 새로고침</button>
    <button id="btn-lock" type="button" title="이 탭에서 보드 키 지우기">잠그기</button>
  </div>
  <div class="cols">
    <section class="col" data-col="pending"><h2>대기 <span class="n">0</span></h2><div class="list"></div></section>
    <section class="col" data-col="in_progress"><h2>진행 <span class="n">0</span></h2><div class="list"></div></section>
    <section class="col" data-col="review"><h2>승인 대기 <span class="n">0</span></h2><div class="list"></div></section>
    <section class="col" data-col="done"><h2>완료 <span class="n">0</span></h2><div class="list"></div></section>
  </div>
</main>

<dialog id="dlg-new" aria-labelledby="new-title">
  <form class="dlg" id="form-new" method="dialog">
    <div class="dlg-head"><h3 id="new-title">새 업무 요청</h3>
      <button class="x" type="button" data-close aria-label="닫기">×</button></div>
    <label for="f-title">제목 *</label>
    <input id="f-title" name="title" maxlength="200" required>
    <label for="f-desc">설명</label>
    <textarea id="f-desc" name="description" maxlength="5000" placeholder="무엇을, 왜, 어떤 결과물로"></textarea>
    <div class="grid2">
      <div><label for="f-assignee">담당자</label>
        <input id="f-assignee" name="assignee" maxlength="64" list="agents" placeholder="비우면 먼저 착수한 에이전트"></div>
      <div><label for="f-priority">우선순위</label>
        <select id="f-priority" name="priority">
          <option value="low">낮음</option><option value="normal" selected>보통</option>
          <option value="high">높음</option><option value="urgent">긴급</option></select></div>
      <div><label for="f-due">기한</label><input id="f-due" name="due" type="date"></div>
      <div><label for="f-division">부서(division)</label><input id="f-division" name="division" maxlength="64"></div>
      <div><label for="f-sens">공개 범위</label>
        <select id="f-sens" name="sensitivity" aria-describedby="f-sens-help">
          <option value="internal" selected>내부</option>
          <option value="confidential">기밀</option></select>
        <div id="f-sens-help" class="meta-line" style="margin-top:4px">기밀: 에이전트에 비공개</div></div>
    </div>
    <div class="err" id="new-err" role="alert"></div>
    <div class="act" style="justify-content:flex-end">
      <span></span>
      <button type="button" data-close>취소</button>
      <button class="primary" type="submit">요청 등록</button>
    </div>
  </form>
</dialog>
<datalist id="agents"></datalist>

<dialog id="dlg-task" aria-labelledby="d-title">
  <div class="dlg" id="task-body"></div>
</dialog>

<div id="toast" class="toast hidden" role="status" aria-live="polite"></div>

<script>
const LABEL = {pending: "대기", in_progress: "진행", blocked: "막힘", review: "승인 대기", done: "완료"};
const PRIO = {urgent: "긴급", high: "높음", normal: "보통", low: "낮음"};
const KIND = {created: "요청", assigned: "담당 지정", claimed: "착수", blocked: "막힘",
              unblocked: "막힘 해제", reported: "보고", approved: "승인", rejected: "반려",
              commented: "코멘트"};
const DONE_LIMIT = 20;
const KEY_SLOT = "brainkit.boardKey";
let state = {tasks: [], summary: null, owner: "대표", filter: "all", openId: null};
let key = "";
try { key = sessionStorage.getItem(KEY_SLOT) || ""; } catch (e) {}

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c =>
  ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c])); }
function today() { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 10); }
function isLate(t) { return t.due && t.status !== "done" && t.due < today(); }
function when(iso) { return iso ? iso.replace("T", " ").slice(0, 16) : ""; }

let toastTimer;
function toast(msg, kind = "ok") {
  const el = $("#toast"); el.textContent = msg; el.className = "toast " + kind;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.add("hidden"), 3500);
}

async function api(path, body) {
  const opt = {method: body ? "POST" : "GET", headers: {"X-Brain-Board-Key": key}};
  if (body) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  let r;
  try { r = await fetch(path, opt); }
  catch (e) { throw new Error("서버에 연결할 수 없습니다 — 대시보드가 실행 중인지 확인하세요"); }
  let data = {};
  try { data = await r.json(); } catch (e) {}
  if (r.status === 401) { lock("보드 키가 올바르지 않습니다"); throw new Error(data.error || "인증 실패"); }
  if (r.status === 503) { showDisabled(data.error); throw new Error(data.error); }
  if (!r.ok) throw new Error(data.error || ("오류 " + r.status));
  return data;
}

function showDisabled(msg) {
  $("#app").classList.add("hidden"); $("#gate").classList.add("hidden");
  const n = $("#disabled"); n.textContent = msg || "업무 보드가 꺼져 있습니다"; n.classList.remove("hidden");
}
function lock(err = "") {
  key = ""; try { sessionStorage.removeItem(KEY_SLOT); } catch (e) {}
  $$("dialog").forEach(d => d.open && d.close());
  $("#app").classList.add("hidden"); $("#gate").classList.remove("hidden");
  $("#gate-err").textContent = err; $("#gate-key").value = ""; $("#gate-key").focus();
}

async function load(quiet = false) {
  if (!key) { lock(); return; }
  try {
    const d = await api("/api/tasks");
    state.tasks = d.tasks; state.summary = d.summary; state.owner = d.owner;
    $("#gate").classList.add("hidden"); $("#disabled").classList.add("hidden");
    $("#app").classList.remove("hidden");
    render();
    $("#updated").textContent = "갱신 " + new Date().toLocaleTimeString("ko-KR", {hour: "2-digit", minute: "2-digit"});
  } catch (e) { if (!quiet && key) toast(e.message, "bad"); }
}

function matches(t) {
  if (state.filter === "review") return t.status === "review";
  if (state.filter === "blocked") return t.status === "blocked";
  if (state.filter === "overdue") return isLate(t);
  return true;
}

function card(t) {
  const late = isLate(t);
  return `<button type="button" class="card${matches(t) ? "" : " dim"}" data-id="${t.id}">
    <div class="m"><span class="badge p-${esc(t.priority)}">${esc(PRIO[t.priority] || t.priority)}</span>
      ${t.status === "blocked" ? '<span class="badge s-blocked">막힘</span>' : ""}
      ${t.sensitivity !== "internal" ? '<span class="badge">기밀</span>' : ""}
      <span>#${t.id}</span></div>
    <div class="t">${esc(t.title)}</div>
    <div class="m"><span>👤 ${t.assignee ? esc(t.assignee) : "미배정"}</span>
      ${t.due ? `<span class="${late ? "late" : ""}">📅 ${esc(t.due)}${late ? " 지남" : ""}</span>` : ""}</div>
  </button>`;
}

function render() {
  const s = state.summary || {counts: {}};
  $("#n-all").textContent = s.total || 0;
  $("#n-review").textContent = s.awaiting_approval || 0;
  $("#n-blocked").textContent = s.blocked || 0;
  $("#n-overdue").textContent = s.overdue || 0;
  $('[data-filter="review"]').classList.toggle("alert", (s.awaiting_approval || 0) > 0);
  $$(".chip").forEach(c => c.classList.toggle("on", c.dataset.filter === state.filter));
  const groups = {pending: [], in_progress: [], review: [], done: []};
  for (const t of state.tasks) (groups[t.status === "blocked" ? "in_progress" : t.status] || []).push(t);
  groups.done.sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""));
  for (const [col, items] of Object.entries(groups)) {
    const sec = $(`[data-col="${col}"]`);
    const shown = col === "done" ? items.slice(0, DONE_LIMIT) : items;
    $(".n", sec).textContent = items.length;
    $(".list", sec).innerHTML = shown.length ? shown.map(card).join("") +
      (items.length > shown.length ? `<div class="empty">최근 ${DONE_LIMIT}건만 표시</div>` : "")
      : '<div class="empty">없음</div>';
    sec.classList.toggle("hl", state.filter === "review" && col === "review");
  }
  const agents = [...new Set(state.tasks.map(t => t.assignee).filter(Boolean))];
  $("#agents").innerHTML = agents.map(a => `<option value="${esc(a)}">`).join("");
}

function actionsFor(t) {
  const a = [];
  if (t.status === "review") a.push(`
    <div class="act"><textarea id="a-note" placeholder="승인 메모(선택) 또는 반려 사유(필수)" maxlength="5000"></textarea></div>
    <div class="act" style="justify-content:flex-end"><span></span>
      <button class="bad" type="button" data-act="reject">반려</button>
      <button class="ok" type="button" data-act="approve">승인</button></div>`);
  if (t.status === "in_progress") a.push(`
    <div class="act"><input id="a-reason" maxlength="5000" placeholder="막힌 이유" aria-label="막힌 이유">
      <button type="button" data-act="block">막힘 처리</button></div>`);
  if (t.status === "blocked") a.push(`
    <div class="act"><input id="a-unblock" maxlength="5000" placeholder="해결 메모(선택)" aria-label="해결 메모">
      <button type="button" data-act="unblock">막힘 해제</button></div>`);
  if (t.status !== "done") a.push(`
    <div class="act"><input id="a-assignee" maxlength="64" list="agents" value="${esc(t.assignee)}" placeholder="담당자 이름" aria-label="담당자">
      <button type="button" data-act="assign">담당 지정</button></div>`);
  a.push(`<div class="act"><textarea id="a-comment" maxlength="5000" placeholder="코멘트" aria-label="코멘트"></textarea>
      <button type="button" data-act="comment">등록</button></div>`);
  return a.join("");
}

// refresh=true: only re-render a detail that is still open (never re-open
// one the user closed while a request was in flight).
async function openTask(id, refresh = false) {
  let t;
  try { t = await api("/api/tasks/" + id); } catch (e) { toast(e.message, "bad"); return; }
  if (refresh && !($("#dlg-task").open && state.openId === id)) return;
  state.openId = id;
  const late = isLate(t);
  const outs = (t.outputs || []).map(o => `<li>${esc(o)}</li>`).join("");
  const hist = (t.events || []).slice().reverse().map(e => `<li>
      <div class="when">${esc(when(e.at))} · ${esc(e.actor)}</div>
      <div><span class="what">${esc(KIND[e.kind] || e.kind)}</span>${e.text ? " — " : ""}<span class="pre">${esc(e.text)}</span></div></li>`).join("");
  $("#task-body").innerHTML = `
    <div class="dlg-head"><div>
        <div class="m" style="display:flex;gap:6px;margin-bottom:6px">
          <span class="badge s-${esc(t.status)}">${esc(LABEL[t.status])}</span>
          <span class="badge p-${esc(t.priority)}">${esc(PRIO[t.priority] || t.priority)}</span>
          <span class="meta-line">#${t.id}</span></div>
        <h3 id="d-title">${esc(t.title)}</h3></div>
      <button class="x" type="button" data-close aria-label="닫기">×</button></div>
    <div class="grid2">
      <div class="kv"><div class="k">요청자</div><div class="v">${esc(t.requester)}</div></div>
      <div class="kv"><div class="k">담당자</div><div class="v">${t.assignee ? esc(t.assignee) : "미배정"}</div></div>
      <div class="kv"><div class="k">기한</div><div class="v ${late ? "late" : ""}">${t.due ? esc(t.due) + (late ? " (지남)" : "") : "—"}</div></div>
      <div class="kv"><div class="k">부서 · 공개 범위</div><div class="v">${esc(t.division || "—")} · ${t.sensitivity === "internal" ? "내부" : "기밀"}</div></div>
    </div>
    ${t.description ? `<div class="sec"><h4>설명</h4><div class="pre">${esc(t.description)}</div></div>` : ""}
    ${outs ? `<div class="sec"><h4>산출물</h4><ul style="margin:0;padding-left:18px">${outs}</ul></div>` : ""}
    ${t.lessons ? `<div class="sec"><h4>교훈</h4><div class="pre">${esc(t.lessons)}</div></div>` : ""}
    <div class="sec"><h4>이력</h4><ul class="hist">${hist}</ul></div>
    <div class="actions">${actionsFor(t)}</div>`;
  const dlg = $("#dlg-task");
  if (!dlg.open) dlg.showModal();
}

async function act(kind) {
  const id = state.openId; if (!id) return;
  const v = sel => (($(sel) || {}).value || "").trim();
  let body;
  if (kind === "approve") body = {note: v("#a-note")};
  else if (kind === "reject") { body = {reason: v("#a-note")};
    if (!body.reason) { toast("반려 사유를 입력하세요", "bad"); $("#a-note").focus(); return; } }
  else if (kind === "block") { body = {reason: v("#a-reason")};
    if (!body.reason) { toast("막힌 이유를 입력하세요", "bad"); $("#a-reason").focus(); return; } }
  else if (kind === "unblock") body = {note: v("#a-unblock")};
  else if (kind === "assign") { body = {assignee: v("#a-assignee")};
    if (!body.assignee) { toast("담당자 이름을 입력하세요", "bad"); $("#a-assignee").focus(); return; } }
  else if (kind === "comment") { body = {text: v("#a-comment")};
    if (!body.text) { toast("코멘트를 입력하세요", "bad"); $("#a-comment").focus(); return; } }
  $$("#task-body button").forEach(b => b.disabled = true);
  try {
    const t = await api(`/api/tasks/${id}/${kind}`, body);
    const msg = {approve: "승인했습니다", reject: "반려했습니다", block: "막힘으로 표시했습니다",
                 unblock: "막힘을 해제했습니다", assign: "담당자를 지정했습니다", comment: "코멘트를 등록했습니다"}[kind];
    toast(t.export_error ? msg + " (위키 내보내기 실패: " + t.export_error + ")" : msg,
          t.export_error ? "bad" : "ok");
    await load(true);
    await openTask(id, true);
  } catch (e) { toast(e.message, "bad"); }
  finally { $$("#task-body button").forEach(b => b.disabled = false); }
}

// ── events ──
$("#gate").addEventListener("submit", e => {
  e.preventDefault();
  key = $("#gate-key").value.trim(); if (!key) return;
  try { sessionStorage.setItem(KEY_SLOT, key); } catch (e) {}
  $("#gate-err").textContent = ""; load();
});
$("#btn-lock").addEventListener("click", () => lock());
$("#btn-refresh").addEventListener("click", () => load());
$$(".chip").forEach(c => c.addEventListener("click", () => { state.filter = c.dataset.filter; render(); }));
$(".cols").addEventListener("click", e => { const c = e.target.closest(".card"); if (c) openTask(+c.dataset.id); });
$("#task-body").addEventListener("click", e => {
  if (e.target.closest("[data-close]")) { $("#dlg-task").close(); return; }
  const b = e.target.closest("[data-act]"); if (b) act(b.dataset.act);
});
$("#dlg-task").addEventListener("close", () => { state.openId = null; });
$("#btn-new").addEventListener("click", () => {
  $("#form-new").reset(); $("#new-err").textContent = ""; $("#dlg-new").showModal(); $("#f-title").focus(); });
$("#dlg-new").addEventListener("click", e => { if (e.target.closest("[data-close]")) $("#dlg-new").close(); });
$("#form-new").addEventListener("submit", async e => {
  e.preventDefault();
  const body = Object.fromEntries(new FormData(e.target).entries());
  body.title = (body.title || "").trim();
  if (!body.title) { $("#new-err").textContent = "제목을 입력하세요"; return; }
  const btn = $('#form-new button[type="submit"]'); btn.disabled = true;
  try {
    const t = await api("/api/tasks", body);
    $("#dlg-new").close(); toast(`#${t.id} 업무를 등록했습니다`); await load(true);
  } catch (err) { $("#new-err").textContent = err.message; }
  finally { btn.disabled = false; }
});
// Click on the backdrop closes a dialog.
$$("dialog").forEach(d => d.addEventListener("click", e => { if (e.target === d) d.close(); }));

load();
setInterval(() => { if (key && !$$("dialog").some(d => d.open)) load(true); }, 30000);
</script>
</body>
</html>
"""
