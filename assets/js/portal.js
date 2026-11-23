/* =====================================================================
 * St. Joseph's Convent School portal - data layer + UI logic
 *
 * Talks to Supabase using the URL + anon key from config.js (generated
 * from .env by serve.py). If no keys are configured, the portal runs in
 * DEMO MODE with sample data so the UI can still be shown.
 * ===================================================================== */

const CFG = window.SUPABASE_CONFIG || {};
const DEMO = !(CFG.url && CFG.anonKey && window.supabase);
const sb = DEMO ? null : window.supabase.createClient(CFG.url, CFG.anonKey);

const THRESHOLD = 75;          // board minimum attendance %
const PAGE = 1000;             // Supabase returns at most 1000 rows per request

// ---------------------------------------------------------------------
// State
// ---------------------------------------------------------------------
let me = null;                 // staff row of the signed-in user
let sections = [];             // [{id, code, standard, division, room, class_teacher_id}]
let students = [];             // see toStudent()
let currentSectionCode = null;
let currentDate = todayISO();

// ---------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------
function todayISO() {
  const d = new Date();
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
  ));
}

function $(id) { return document.getElementById(id); }

function sectionByCode(code) { return sections.find(s => s.code === code); }
function sectionById(id) { return sections.find(s => s.id === id); }
function sectionLabel(sec) { return sec ? `${sec.standard} — Section ${sec.division}` : ''; }
function sectionStudents(code) {
  return students.filter(s => s.section === code).sort((a, b) => a.roll - b.roll);
}

function weight(status) {
  if (status === 'HALF_DAY') return 0.5;
  if (status === 'ABSENT') return 0;
  return 1; // PRESENT, LATE, LEAVE
}

function showError(err, context) {
  console.error(context, err);
  alert(`${context}: ${err?.message || err}`);
}

/** Fetch every row of a query, 1000 at a time. */
async function fetchAll(buildQuery) {
  const rows = [];
  for (let from = 0; ; from += PAGE) {
    const { data, error } = await buildQuery().range(from, from + PAGE - 1);
    if (error) throw error;
    rows.push(...data);
    if (data.length < PAGE) return rows;
  }
}

function toStudent(row) {
  const sec = sectionById(row.section_id);
  return {
    id: row.id,
    adm: row.admission_number,
    roll: row.roll_number,
    name: row.full_name,
    sectionId: row.section_id,
    section: sec ? sec.code : '',
    parent: row.parent_name || '',
    phone: row.phone || '',
    attendance: 100.0,   // filled from student_attendance_summary
    totalDays: 0,
    streak: 0,
    status: 'PRESENT',   // today's status (default = present, mark exceptions)
    marked: false,       // true if a row exists in the DB for currentDate
  };
}

// ---------------------------------------------------------------------
// Demo data (used only when .env has no Supabase keys)
// ---------------------------------------------------------------------
function loadDemoData() {
  sections = [
    { id: 1, code: '10A', standard: '10th Standard', division: 'A', room: 'Room 102', class_teacher_id: 'demo' },
    { id: 2, code: '10B', standard: '10th Standard', division: 'B', room: 'Room 103', class_teacher_id: null },
    { id: 3, code: '9A', standard: '9th Standard', division: 'A', room: 'Room 101', class_teacher_id: null },
  ];
  const raw = [
    [1, "Aaron D'Souza", "David D'Souza", "9845112233", 95.2, "PRESENT"],
    [2, "Aishwarya Rao", "Ramesh Rao", "9845223344", 92.1, "PRESENT"],
    [3, "Allen Peter", "Peter Francis", "9845334455", 88.5, "PRESENT"],
    [4, "Bhavana Suresh", "Suresh Gowda", "9845445566", 94.0, "PRESENT"],
    [5, "Daniel Rodrigues", "Joseph Rodrigues", "9845556677", 86.4, "PRESENT"],
    [6, "Divya Mary", "Anthony Swamy", "9845667788", 96.0, "PRESENT"],
    [7, "Immanuel Raj", "Raj Kumar", "9845778899", 82.5, "PRESENT"],
    [8, "Jennie Fernandez", "Martin Fernandez", "9845889900", 91.0, "PRESENT"],
    [9, "Joshua Thomas", "Thomas Mathew", "9845990011", 89.2, "PRESENT"],
    [10, "Kavya Murthy", "S. N. Murthy", "9845012345", 68.4, "ABSENT"],
    [11, "Kiran Kumar", "Venkatesh K.", "9845123456", 84.1, "PRESENT"],
    [12, "Lavanya S.", "Somashekar B.", "9845234567", 90.0, "PRESENT"],
    [13, "Mohammed Zeeshan", "Mohammed Ismail", "9880098765", 71.2, "ABSENT"],
    [14, "Nisha Clement", "Clement D.", "9845456789", 87.0, "PRESENT"],
    [15, "Pooja Hegde", "Ananth Hegde", "9845567890", 93.5, "PRESENT"],
    [16, "Preetham Paul", "Paul V.", "9845678901", 85.0, "PRESENT"],
    [17, "Rahul Benedict", "Benedict Xavier", "9845789012", 81.3, "PRESENT"],
    [18, "Ria Ann George", "George K.", "9845890123", 97.4, "PRESENT"],
    [19, "Roshan Francis", "Francis Xavier", "9900112233", 73.8, "ABSENT"],
    [20, "Sneha Manjunath", "Manjunath C.", "9900223344", 79.5, "ABSENT"],
  ];
  students = raw.map(([roll, name, parent, phone, att, status]) => ({
    id: roll, adm: `SJ-2022-${String(roll).padStart(3, '0')}`, roll, name,
    sectionId: 1, section: '10A', parent, phone, attendance: att, totalDays: 24,
    streak: att < 75 ? 3 : 0, status, marked: false,
  }));
  me = { id: 'demo', full_name: 'Sr. Teresa', role: 'TEACHER' };
}

// ---------------------------------------------------------------------
// Supabase loading
// ---------------------------------------------------------------------
async function loadAll() {
  const { data: secRows, error: secErr } = await sb
    .from('sections')
    .select('id, code, standard, division, room, class_teacher_id')
    .order('sort_order').order('code');
  if (secErr) throw secErr;
  sections = secRows;

  const studentRows = await fetchAll(() => sb
    .from('students')
    .select('id, admission_number, roll_number, full_name, section_id, parent_name, phone')
    .eq('status', 'ACTIVE')
    .order('id'));
  students = studentRows.map(toStudent);

  await Promise.all([loadSummary(), loadAttendanceForDate(currentDate)]);
}

async function loadSummary() {
  const rows = await fetchAll(() => sb
    .from('student_attendance_summary')
    .select('student_id, total_days, attendance_percent, consecutive_absences')
    .order('student_id'));
  const byId = new Map(rows.map(r => [r.student_id, r]));
  students.forEach(s => {
    const r = byId.get(s.id);
    s.attendance = r ? Number(r.attendance_percent) : 100.0;
    s.totalDays = r ? r.total_days : 0;
    s.streak = r ? r.consecutive_absences : 0;
  });
}

async function loadAttendanceForDate(day) {
  const rows = await fetchAll(() => sb
    .from('attendance')
    .select('student_id, status')
    .eq('date', day)
    .order('id'));
  const byId = new Map(rows.map(r => [r.student_id, r.status]));
  students.forEach(s => {
    s.marked = byId.has(s.id);
    s.status = byId.get(s.id) || 'PRESENT';
  });
}

// ---------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------
function showLogin(message = '') {
  $('login-overlay').classList.remove('hidden');
  $('login-form').classList.remove('hidden');
  $('login-not-staff').classList.add('hidden');
  $('login-error').textContent = message;
}

function hideLogin() { $('login-overlay').classList.add('hidden'); }

async function handleLogin(event) {
  event.preventDefault();
  const btn = $('login-submit');
  btn.disabled = true;
  $('login-error').textContent = '';
  const { error } = await sb.auth.signInWithPassword({
    email: $('login-email').value.trim(),
    password: $('login-password').value,
  });
  btn.disabled = false;
  if (error) $('login-error').textContent = error.message;
  // On success, onAuthStateChange takes over.
}

async function signOut() {
  if (DEMO) { alert('Demo mode: no one is signed in.'); return; }
  await sb.auth.signOut();
}

async function onSignedIn(user) {
  // supabase-js can fire SIGNED_IN again on tab refocus; don't wipe unsaved marks.
  if (me && me.id === user.id) return;
  const { data, error } = await sb.from('staff').select('id, full_name, role').eq('id', user.id).maybeSingle();
  if (error) { showError(error, 'Could not load your staff profile'); return; }
  if (!data) {
    $('login-overlay').classList.remove('hidden');
    $('login-form').classList.add('hidden');
    $('login-not-staff').classList.remove('hidden');
    $('login-not-staff-email').textContent = user.email;
    return;
  }
  me = data;
  hideLogin();
  try {
    await loadAll();
  } catch (err) {
    showError(err, 'Could not load data from Supabase');
  }
  afterDataLoaded();
}

// ---------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------
function afterDataLoaded() {
  if (!currentSectionCode || !sectionByCode(currentSectionCode)) {
    const mine = sections.find(s => me && s.class_teacher_id === me.id);
    currentSectionCode = (mine || sections[0] || {}).code || null;
  }
  renderUser();
  populateSectionSelects();
  renderAll();
}

function renderAll() {
  renderAttendanceTitle();
  renderAttendanceRoster();
  renderAbsenteesTable();
  filterStudents();
  updateDashboardCounts();
  renderAssignedClasses();
  renderAttentionList();
  renderPendingAlert();
}

function renderUser() {
  if (!me) return;
  const roleLabel = { ADMIN: 'Administrator', PRINCIPAL: 'Principal', TEACHER: 'Teacher' }[me.role] || me.role;
  const mine = sections.find(s => s.class_teacher_id === me.id);
  $('user-name').textContent = mine ? `${me.full_name}, Class Teacher` : `${me.full_name}, ${roleLabel}`;
  $('user-subtitle').textContent = mine ? sectionLabel(mine) : roleLabel;
  $('user-avatar').textContent = (me.full_name.replace(/^(Sr|Fr|Mr|Mrs|Ms|Dr)\.?\s+/i, '')[0] || '?').toUpperCase();
  const hour = new Date().getHours();
  const greet = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
  $('welcome-heading').textContent = `${greet}, ${me.full_name} 👋`;
}

function populateSectionSelects() {
  const options = sections.map(s =>
    `<option value="${esc(s.code)}">${esc(s.standard)} - Sec ${esc(s.division)}</option>`).join('');

  const filter = $('class-filter-select');
  const prevFilter = filter.value;
  filter.innerHTML = `<option value="ALL">All Sections</option>` + options;
  filter.value = sections.some(s => s.code === prevFilter) ? prevFilter : (currentSectionCode || 'ALL');

  ['new-section', 'import-section', 'report-section'].forEach(id => {
    const el = $(id);
    if (!el) return;
    el.innerHTML = options;
    if (currentSectionCode) el.value = currentSectionCode;
  });
}

function renderAttendanceTitle() {
  const sec = sectionByCode(currentSectionCode);
  $('attendance-section-title').textContent = sec ? sectionLabel(sec) : 'No sections yet';
  $('absentees-section-label').textContent = sec ? `Absentees · ${sec.code} · ${currentDate}` : 'Absentees';
}

function selectClassForAttendance(code) {
  currentSectionCode = code;
  $('attendance-save-banner').classList.add('hidden');
  renderAttendanceTitle();
  renderAttendanceRoster();
  renderAbsenteesTable();
  updateDashboardCounts();
  switchTab('attendance');
}

function renderAttendanceRoster() {
  const container = $('attendance-roster-container');
  if (!container) return;
  const list = sectionStudents(currentSectionCode);

  if (list.length === 0) {
    container.innerHTML = `<div class="p-6 text-center text-xs text-[var(--text-muted)]">No students in this section yet. Add them from Student Records or Excel Import.</div>`;
    updateAttendanceCounters();
    return;
  }

  const pill = (s, value, label, on) => `
    <button onclick="setStatus(${s.id}, '${value}')" class="px-2.5 py-1.5 rounded-lg text-xs font-bold transition ${s.status === value ? on + ' text-white shadow-sm' : 'border border-[var(--border-soft)] text-slate-400'}">${label}</button>`;

  container.innerHTML = list.map(s => `
    <div class="p-3 sm:p-4 flex items-center justify-between flex-wrap gap-2 hover:bg-[var(--bg-cream)] transition-colors">
      <div class="flex items-center gap-3">
        <span class="w-7 text-xs font-mono font-bold text-slate-400">#${esc(s.roll)}</span>
        <div>
          <div class="font-heading font-semibold text-xs sm:text-sm text-[var(--text-dark)]">${esc(s.name)}</div>
          <div class="text-[11px] text-[var(--text-muted)]">
            Cumulative Attendance:
            <span class="font-bold ${s.attendance < THRESHOLD ? 'text-red-600' : 'text-slate-500'}">${esc(s.attendance)}%</span>
            ${s.marked ? '' : '<span class="ml-1 text-amber-600">· not saved</span>'}
          </div>
        </div>
      </div>
      <div class="flex items-center gap-1.5" role="group" aria-label="Status for ${esc(s.name)}">
        ${pill(s, 'PRESENT', 'P', 'bg-emerald-600')}
        ${pill(s, 'ABSENT', 'A', 'bg-red-600')}
        ${pill(s, 'LATE', 'L', 'bg-amber-500')}
        ${pill(s, 'HALF_DAY', 'H', 'bg-blue-600')}
        ${pill(s, 'LEAVE', 'Lv', 'bg-slate-600')}
      </div>
    </div>`).join('');

  updateAttendanceCounters();
}

function setStatus(id, newStatus) {
  const s = students.find(x => x.id === id);
  if (!s) return;
  s.status = newStatus;
  renderAttendanceRoster();
  renderAbsenteesTable();
  updateDashboardCounts();
}

function markAllStatus(value) {
  sectionStudents(currentSectionCode).forEach(s => { s.status = value; });
  renderAttendanceRoster();
  renderAbsenteesTable();
  updateDashboardCounts();
}

function updateAttendanceCounters() {
  const list = sectionStudents(currentSectionCode);
  const present = list.filter(s => s.status === 'PRESENT' || s.status === 'LATE').length;
  const absent = list.filter(s => s.status === 'ABSENT').length;
  const late = list.filter(s => s.status === 'LATE').length;
  $('live-present-count').textContent = present;
  $('live-absent-count').textContent = absent;
  $('live-late-count').textContent = late;
  $('badge-absent-count').textContent = absent;
}

function updateDashboardCounts() {
  const sec = sectionByCode(currentSectionCode);
  const list = sectionStudents(currentSectionCode);
  const present = list.filter(s => s.status === 'PRESENT' || s.status === 'LATE').length;
  const absent = list.filter(s => s.status === 'ABSENT').length;
  const pct = list.length ? (list.reduce((sum, s) => sum + weight(s.status), 0) / list.length * 100).toFixed(1) : '0.0';

  $('kpi-total').textContent = students.length.toLocaleString('en-IN');
  $('kpi-total-sub').textContent = sec ? `${list.length} students in ${sec.code}` : 'No sections yet';
  $('kpi-present').textContent = present;
  $('kpi-present-sub').textContent = sec ? `In ${sectionLabel(sec)}` : '';
  $('kpi-absent').textContent = absent;
  $('kpi-percent').textContent = pct + '%';
}

async function saveAttendance() {
  const sec = sectionByCode(currentSectionCode);
  const list = sectionStudents(currentSectionCode);
  if (!sec || list.length === 0) { alert('There are no students in this section to save.'); return; }

  if (!DEMO) {
    const rows = list.map(s => ({ student_id: s.id, section_id: sec.id, date: currentDate, status: s.status }));
    const { error } = await sb.from('attendance').upsert(rows, { onConflict: 'student_id,date' });
    if (error) { showError(error, 'Attendance was NOT saved'); return; }
    try { await loadSummary(); } catch (err) { console.error(err); }
  }
  list.forEach(s => { s.marked = true; });

  $('attendance-save-text').textContent = `Attendance saved for ${list.length} students in ${sec.code} on ${currentDate}.`;
  const banner = $('attendance-save-banner');
  banner.classList.remove('hidden');
  renderAll();
  setTimeout(() => banner.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 50);
}

async function onAttendanceDateChange(value) {
  if (!value) return;
  currentDate = value;
  $('attendance-save-banner').classList.add('hidden');
  if (!DEMO) {
    try { await loadAttendanceForDate(currentDate); } catch (err) { showError(err, 'Could not load attendance'); }
  }
  renderAll();
}

// ---------------------------------------------------------------------
// Absentees & WhatsApp
// ---------------------------------------------------------------------
function absenceMessage(s) {
  return `Dear Parent, St. Joseph's Convent High School Sumanahalli informs you that your ward ${s.name} (Class ${s.section}, Roll No ${s.roll}) was marked ABSENT today. Please contact the class teacher or school office if this was unplanned.`;
}

function lowAttendanceMessage(s) {
  return `Dear Parent, St. Joseph's Convent High School Sumanahalli informs you that your ward ${s.name} (Class ${s.section}) has attendance below the ${THRESHOLD}% required board threshold. Please meet the class teacher at the school office.`;
}

function logWhatsApp(s, type, message) {
  if (DEMO) return;
  sb.from('whatsapp_log')
    .insert({ student_id: s.id, phone: s.phone, message_type: type, message, for_date: currentDate })
    .then(({ error }) => { if (error) console.error('WhatsApp log failed', error); });
}

function openWhatsApp(studentId, type) {
  const s = students.find(x => x.id === studentId);
  if (!s) return;
  if (!s.phone) { alert(`No phone number saved for ${s.name}.`); return; }
  const message = type === 'ABSENCE' ? absenceMessage(s) : lowAttendanceMessage(s);
  window.open(`https://wa.me/91${s.phone}?text=${encodeURIComponent(message)}`, '_blank', 'noopener');
  logWhatsApp(s, type, message);
}

function renderAbsenteesTable() {
  const tbody = $('absentees-table-body');
  if (!tbody) return;
  const absentees = sectionStudents(currentSectionCode).filter(s => s.status === 'ABSENT');
  $('notify-all-text').textContent = `Notify All ${absentees.length} Parents via WhatsApp`;

  if (absentees.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="p-6 text-center text-[var(--text-muted)]">No students absent! All students present.</td></tr>`;
    return;
  }

  tbody.innerHTML = absentees.map(s => {
    const days = Math.max(s.streak + (s.marked ? 0 : 1), 1);
    const critical = days >= 3;
    return `
      <tr class="hover:bg-[var(--bg-cream)] transition-colors">
        <td class="py-3 px-4 font-mono font-bold text-slate-400">#${esc(s.roll)}</td>
        <td class="py-3 px-4 font-semibold text-[var(--text-dark)]">${esc(s.name)}</td>
        <td class="py-3 px-4">
          <span class="inline-block px-2 py-0.5 rounded-full ${critical ? 'bg-red-100 text-red-700 font-bold' : 'bg-amber-100 text-amber-800'} text-[10px]">
            ${days} Day${days > 1 ? 's' : ''}${critical ? ' (Critical)' : ''}
          </span>
        </td>
        <td class="py-3 px-4 text-[var(--text-muted)]">${esc(s.parent)}</td>
        <td class="py-3 px-4 font-mono">${esc(s.phone)}</td>
        <td class="py-3 px-4 text-right">
          <button onclick="openWhatsApp(${s.id}, 'ABSENCE')" class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs shadow-sm transition">
            <span>WhatsApp Parent</span>
          </button>
        </td>
      </tr>`;
  }).join('');
}

function notifyAllWhatsApp() {
  const absentees = sectionStudents(currentSectionCode).filter(s => s.status === 'ABSENT');
  alert(`${absentees.length} absent students. Browsers block opening many chats at once, so use the "WhatsApp Parent" button on each row - each message is logged.`);
}

// ---------------------------------------------------------------------
// Dashboard panels
// ---------------------------------------------------------------------
function renderAssignedClasses() {
  const box = $('assigned-classes');
  if (!box) return;
  const mine = sections.filter(s => me && s.class_teacher_id === me.id);
  const list = mine.length ? [...mine, ...sections.filter(s => !mine.includes(s))] : sections;
  if (list.length === 0) {
    box.innerHTML = `<p class="text-xs text-[var(--text-muted)]">No sections created yet.</p>`;
    return;
  }
  box.innerHTML = list.map(s => {
    const count = sectionStudents(s.code).length;
    const isMine = mine.includes(s);
    return `
      <div class="p-4 rounded-xl bg-[var(--bg-cream)] border border-[var(--border-soft)] flex items-center justify-between">
        <div>
          <div class="font-heading font-bold text-sm text-[var(--text-dark)]">${esc(sectionLabel(s))}</div>
          <div class="text-xs text-[var(--text-muted)]">${isMine ? 'You are the class teacher · ' : ''}${count} Students${s.room ? ' · ' + esc(s.room) : ''}</div>
        </div>
        <button onclick="selectClassForAttendance('${esc(s.code)}')" class="px-3.5 py-1.5 rounded-lg ${isMine ? 'bg-[#D45129] text-white hover:bg-[#A83515]' : 'border border-[#D45129] text-[#D45129] hover:bg-[#D45129] hover:text-white'} font-semibold text-xs transition">
          <span>Mark &rarr;</span>
        </button>
      </div>`;
  }).join('');
}

function renderAttentionList() {
  const box = $('attention-list');
  if (!box) return;
  const low = students
    .filter(s => s.totalDays > 0 && s.attendance < THRESHOLD)
    .sort((a, b) => a.attendance - b.attendance)
    .slice(0, 8);
  if (low.length === 0) {
    box.innerHTML = `<p class="py-3 text-[var(--text-muted)]">No students below ${THRESHOLD}%.</p>`;
    return;
  }
  box.innerHTML = low.map(s => `
    <div class="py-3 flex items-center justify-between">
      <div>
        <div class="font-semibold text-[var(--text-dark)]">${esc(s.name)}</div>
        <div class="text-[11px] text-[var(--text-muted)]">Roll No: ${esc(s.roll)} · ${esc(s.section)}${s.streak ? ` · ${s.streak} Consecutive Absence${s.streak > 1 ? 's' : ''}` : ''}</div>
      </div>
      <div class="text-right">
        <span class="font-bold text-red-600 text-sm">${esc(s.attendance)}%</span>
        <button onclick="openWhatsApp(${s.id}, 'LOW_ATTENDANCE')" class="block text-[11px] text-[#0284C7] hover:underline font-medium">WhatsApp Parent</button>
      </div>
    </div>`).join('');
}

function renderPendingAlert() {
  const box = $('pending-alert');
  if (!box) return;
  const pending = sections.filter(sec => {
    const list = sectionStudents(sec.code);
    return list.length > 0 && !list.some(s => s.marked);
  });
  if (DEMO || pending.length === 0) { box.classList.add('hidden'); return; }
  box.classList.remove('hidden');
  $('pending-title').textContent = `Attendance not yet submitted for ${pending.length} section${pending.length > 1 ? 's' : ''}`;
  $('pending-text').textContent = `${pending.map(sectionLabel).join(', ')} ${pending.length > 1 ? 'have' : 'has'} not saved a register for ${currentDate}.`;
  $('pending-buttons').innerHTML = pending.slice(0, 4).map(sec => `
    <button onclick="selectClassForAttendance('${esc(sec.code)}')" class="px-3.5 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white font-semibold transition">Mark ${esc(sec.code)}</button>`).join('');
}

// ---------------------------------------------------------------------
// Student directory
// ---------------------------------------------------------------------
function renderStudentsDirectory(dataset) {
  const tbody = $('students-table-body');
  if (!tbody) return;
  if (dataset.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="p-6 text-center text-[var(--text-muted)]">No students found.</td></tr>`;
    return;
  }
  tbody.innerHTML = dataset.map(s => `
    <tr class="hover:bg-[var(--bg-cream)] transition-colors">
      <td class="py-3 px-4 font-mono text-slate-400">#${esc(s.roll)}</td>
      <td class="py-3 px-4 font-mono text-slate-500">${esc(s.adm)}</td>
      <td class="py-3 px-4 font-semibold text-[var(--text-dark)]">${esc(s.name)}</td>
      <td class="py-3 px-4 text-[var(--text-muted)]">${esc(s.section)}</td>
      <td class="py-3 px-4 text-[var(--text-muted)]">
        <div>${esc(s.parent)}</div>
        <div class="font-mono text-[11px] text-slate-400">${esc(s.phone)}</div>
      </td>
      <td class="py-3 px-4">
        <span class="inline-block px-2.5 py-0.5 rounded-full font-bold text-xs ${s.attendance < THRESHOLD ? 'bg-red-100 text-red-700' : 'bg-emerald-100 text-emerald-700'}">${esc(s.attendance)}%</span>
      </td>
      <td class="py-3 px-4 text-right">
        <button onclick="viewStudentDetail(${s.id})" class="px-2.5 py-1 rounded-lg border border-[var(--border-soft)] hover:bg-[#D45129] hover:text-white transition font-medium text-xs">View Profile</button>
      </td>
    </tr>`).join('');
}

function filterStudents() {
  const query = $('student-search-input').value.toLowerCase().trim();
  const sec = $('class-filter-select').value;
  const level = $('status-filter-select').value;
  const filtered = students.filter(s => {
    const matchesQuery = !query || s.name.toLowerCase().includes(query)
      || String(s.roll).includes(query) || String(s.adm).toLowerCase().includes(query);
    const matchesSec = sec === 'ALL' || s.section === sec;
    const matchesLevel = level === 'ALL' || (level === 'LOW' ? s.attendance < THRESHOLD : s.attendance >= 85);
    return matchesQuery && matchesSec && matchesLevel;
  }).sort((a, b) => a.section.localeCompare(b.section) || a.roll - b.roll);
  renderStudentsDirectory(filtered);
}

function viewStudentDetail(id) {
  const s = students.find(x => x.id === id);
  if (!s) return;
  $('detail-name').textContent = s.name;
  $('detail-avatar').textContent = s.name.split(' ').filter(Boolean).map(n => n[0]).join('').slice(0, 3);
  $('detail-meta').textContent = `Roll No: #${s.roll} · Section ${s.section} · KSEEB Board`;
  $('detail-adm').textContent = s.adm;
  $('detail-parent').textContent = s.parent || '—';
  $('detail-phone').textContent = s.phone ? `+91 ${s.phone}` : '—';
  const att = $('detail-attendance');
  att.textContent = `${s.attendance}%`;
  att.className = s.attendance < THRESHOLD ? 'text-red-600 font-bold' : 'text-emerald-600 font-bold';
  $('detail-whatsapp-btn').onclick = () => openWhatsApp(s.id, 'LOW_ATTENDANCE');
  $('modal-student-detail').classList.remove('hidden');
}

function closeStudentDetailModal() { $('modal-student-detail').classList.add('hidden'); }
function openAddStudentModal() { $('modal-add-student').classList.remove('hidden'); }
function closeAddStudentModal() { $('modal-add-student').classList.add('hidden'); }

async function saveNewStudent(event) {
  event.preventDefault();
  const name = $('new-name').value.trim();
  const roll = parseInt($('new-roll').value, 10);
  const sec = sectionByCode($('new-section').value);
  const parent = $('new-parent').value.trim();
  const phone = $('new-phone').value.trim();
  if (!sec) { alert('Please choose a section.'); return; }

  if (DEMO) {
    students.push({
      id: Date.now(), adm: 'SJ-DEMO', roll, name, sectionId: sec.id, section: sec.code,
      parent, phone, attendance: 100.0, totalDays: 0, streak: 0, status: 'PRESENT', marked: false,
    });
  } else {
    const { data, error } = await sb.from('students')
      .insert({ full_name: name, roll_number: roll, section_id: sec.id, parent_name: parent, phone })
      .select('id, admission_number, roll_number, full_name, section_id, parent_name, phone')
      .single();
    if (error) {
      if (error.code === '23505') alert(`Roll number ${roll} already exists in ${sec.code}.`);
      else showError(error, 'Student was NOT saved');
      return;
    }
    students.push(toStudent(data));
  }

  $('add-student-form').reset();
  closeAddStudentModal();
  renderAll();
  alert(`Student ${name} successfully enrolled into ${sec.code}!`);
}

// ---------------------------------------------------------------------
// Excel / CSV import
// ---------------------------------------------------------------------
const IMPORT_HEADERS = {
  roll: ['rollno', 'roll', 'rollnumber', 'rollnum'],
  name: ['fullname', 'name', 'studentname', 'studentfullname'],
  parent: ['parentname', 'parent', 'guardian', 'guardianname', 'parentguardian', 'fathername'],
  phone: ['phone', 'mobile', 'phonenumber', 'mobilenumber', 'mobileno', 'phoneno', 'contact', 'whatsapp'],
  gender: ['gender', 'sex'],
  dob: ['dateofbirth', 'dob', 'birthdate'],
  section: ['section', 'class', 'classsection', 'sec'],
};

function normHeader(h) { return String(h).toLowerCase().replace(/[^a-z0-9]/g, ''); }

function pick(row, field) {
  for (const key of Object.keys(row)) {
    if (IMPORT_HEADERS[field].includes(normHeader(key))) return row[key];
  }
  return '';
}

function parseDob(value) {
  if (!value) return null;
  if (value instanceof Date && !isNaN(value)) {
    const pad = n => String(n).padStart(2, '0');
    return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`;
  }
  const text = String(value).trim();
  let m = text.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (m) return `${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}`;
  m = text.match(/^(\d{1,2})[\/.-](\d{1,2})[\/.-](\d{4})$/); // dd/mm/yyyy (Indian format)
  if (m) return `${m[3]}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}`;
  return null;
}

function parsePhone(value) {
  const digits = String(value ?? '').replace(/\D/g, '');
  return digits.length >= 10 ? digits.slice(-10) : null;
}

async function importExcel(input) {
  const file = input.files && input.files[0];
  input.value = '';
  if (!file) return;
  if (!window.XLSX) { alert('The Excel reader did not load. Check your internet connection.'); return; }

  const defaultSec = sectionByCode($('import-section').value);
  let rows;
  try {
    const wb = XLSX.read(await file.arrayBuffer(), { type: 'array', cellDates: true });
    rows = XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]], { defval: '' });
  } catch (err) {
    showError(err, 'Could not read the file'); return;
  }

  const records = new Map();   // key: section_id|roll -> record (last row wins)
  let skipped = 0;
  for (const row of rows) {
    const name = String(pick(row, 'name')).trim();
    const roll = parseInt(pick(row, 'roll'), 10);
    const secText = String(pick(row, 'section')).replace(/\s+/g, '').toUpperCase();
    const sec = (secText && sections.find(s => s.code.toUpperCase() === secText)) || defaultSec;
    if (!name || !roll || roll < 1 || !sec) { skipped++; continue; }
    records.set(`${sec.id}|${roll}`, {
      full_name: name,
      roll_number: roll,
      section_id: sec.id,
      parent_name: String(pick(row, 'parent')).trim() || null,
      phone: parsePhone(pick(row, 'phone')),
      gender: String(pick(row, 'gender')).trim() || null,
      date_of_birth: parseDob(pick(row, 'dob')),
    });
  }

  const list = [...records.values()];
  if (list.length === 0) {
    alert('No valid rows found. Each row needs at least a Roll No and Full Name (and a Section column, or pick a default section).');
    return;
  }

  if (DEMO) {
    alert(`Demo mode: ${list.length} rows read (${skipped} skipped). Connect Supabase to save them.`);
    return;
  }

  for (let i = 0; i < list.length; i += 500) {
    const { error } = await sb.from('students').upsert(list.slice(i, i + 500), { onConflict: 'section_id,roll_number' });
    if (error) { showError(error, `Import stopped after ${i} rows`); break; }
  }

  try { await loadAll(); } catch (err) { showError(err, 'Could not reload students'); }
  afterDataLoaded();
  alert(`"${file.name}": ${list.length} student records added or updated, ${skipped} rows skipped.`);
  switchTab('students');
}

function downloadTemplate() {
  const csv = 'Roll No,Full Name,Section,Parent Name,Phone,Gender,Date of Birth\n1,Maria Joseph,10A,Joseph Mathew,9845000000,Female,15/06/2011\n';
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  link.download = 'St_Josephs_Student_Import_Template.csv';
  link.click();
  URL.revokeObjectURL(link.href);
}

// ---------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------
function populateReportMonths() {
  const el = $('report-month');
  const now = new Date();
  const opts = [];
  for (let i = 0; i < 12; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
    opts.push(`<option value="${value}">${d.toLocaleDateString('en-IN', { month: 'long', year: 'numeric' })}</option>`);
  }
  el.innerHTML = opts.join('');
}

async function generateReport() {
  const out = $('report-body');
  const sec = sectionByCode($('report-section').value);
  const month = $('report-month').value;
  const type = $('report-type').value;
  if (DEMO) { out.innerHTML = `<p class="text-xs text-center text-[var(--text-muted)]">Connect Supabase (.env) to generate real reports.</p>`; return; }
  if (!sec || !month) return;

  const [y, m] = month.split('-').map(Number);
  const start = `${month}-01`;
  const end = `${month}-${String(new Date(y, m, 0).getDate()).padStart(2, '0')}`;
  const monthLabel = new Date(y, m - 1, 1).toLocaleDateString('en-IN', { month: 'long', year: 'numeric' });
  $('report-subtitle').textContent = `${type === 'LOG' ? 'Parent WhatsApp Log' : 'Monthly Class Attendance Summary'} · ${sectionLabel(sec)} · ${monthLabel}`;
  out.innerHTML = `<p class="text-xs text-center text-[var(--text-muted)]">Loading…</p>`;

  try {
    if (type === 'LOG') {
      const ids = sectionStudents(sec.code).map(s => s.id);
      const rows = ids.length ? await fetchAll(() => sb.from('whatsapp_log')
        .select('student_id, phone, message_type, for_date, sent_at')
        .in('student_id', ids).gte('for_date', start).lte('for_date', end)
        .order('sent_at')) : [];
      const nameOf = id => (students.find(s => s.id === id) || {}).name || id;
      out.innerHTML = rows.length === 0
        ? `<p class="text-xs text-center text-[var(--text-muted)]">No WhatsApp messages logged this month.</p>`
        : `<table class="w-full text-left text-xs"><thead class="text-[var(--text-muted)] uppercase text-[11px]"><tr><th class="py-2">Date</th><th>Student</th><th>Type</th><th>Phone</th></tr></thead><tbody class="divide-y divide-[var(--border-soft)]">${
            rows.map(r => `<tr><td class="py-2">${esc(r.for_date)}</td><td>${esc(nameOf(r.student_id))}</td><td>${r.message_type === 'ABSENCE' ? 'Absence' : 'Low attendance'}</td><td class="font-mono">${esc(r.phone)}</td></tr>`).join('')
          }</tbody></table>`;
      return;
    }

    const rows = await fetchAll(() => sb.from('attendance')
      .select('student_id, date, status')
      .eq('section_id', sec.id).gte('date', start).lte('date', end)
      .order('id'));
    const days = new Set(rows.map(r => r.date)).size;
    const perStudent = new Map();
    rows.forEach(r => {
      const p = perStudent.get(r.student_id) || { total: 0, score: 0, absent: 0 };
      p.total++; p.score += weight(r.status); if (r.status === 'ABSENT') p.absent++;
      perStudent.set(r.student_id, p);
    });
    const avg = rows.length ? (rows.reduce((t, r) => t + weight(r.status), 0) / rows.length * 100).toFixed(1) : '0.0';
    const list = sectionStudents(sec.code).map(s => {
      const p = perStudent.get(s.id) || { total: 0, score: 0, absent: 0 };
      return { ...s, mTotal: p.total, mAbsent: p.absent, mPct: p.total ? +(p.score / p.total * 100).toFixed(1) : null };
    });
    const below = list.filter(s => s.mPct !== null && s.mPct < THRESHOLD);
    const shown = type === 'CHRONIC' ? below.sort((a, b) => a.mPct - b.mPct) : list;

    out.innerHTML = `
      <div class="grid grid-cols-3 gap-4 text-center text-xs py-2 bg-[var(--bg-cream)] rounded-lg">
        <div><strong>Total Working Days:</strong> ${days}</div>
        <div><strong>Average Attendance:</strong> ${avg}%</div>
        <div><strong>Students Below ${THRESHOLD}%:</strong> ${below.length}</div>
      </div>
      ${shown.length === 0 ? `<p class="text-xs text-center text-[var(--text-muted)] pt-3">${type === 'CHRONIC' ? 'No chronic absentees this month.' : 'No students in this section.'}</p>` : `
      <table class="w-full text-left text-xs mt-3"><thead class="text-[var(--text-muted)] uppercase text-[11px]"><tr><th class="py-2">Roll</th><th>Name</th><th>Days Marked</th><th>Absent</th><th>Attendance</th></tr></thead>
      <tbody class="divide-y divide-[var(--border-soft)]">${shown.map(s => `
        <tr><td class="py-2 font-mono">#${esc(s.roll)}</td><td>${esc(s.name)}</td><td>${s.mTotal}</td><td>${s.mAbsent}</td>
        <td class="font-bold ${s.mPct !== null && s.mPct < THRESHOLD ? 'text-red-600' : ''}">${s.mPct === null ? '—' : s.mPct + '%'}</td></tr>`).join('')}
      </tbody></table>`}`;
  } catch (err) {
    out.innerHTML = '';
    showError(err, 'Could not generate report');
  }
}

// ---------------------------------------------------------------------
// Tabs & theme
// ---------------------------------------------------------------------
function switchTab(tabId) {
  document.querySelectorAll('.portal-view').forEach(v => v.classList.add('hidden'));
  const view = $('view-' + tabId);
  if (view) view.classList.remove('hidden');
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.remove('bg-[#D45129]', 'text-white', 'shadow-sm');
    btn.classList.add('text-white/80');
  });
  const nav = $('nav-' + tabId);
  if (nav) {
    nav.classList.add('bg-[#D45129]', 'text-white', 'shadow-sm');
    nav.classList.remove('text-white/80');
  }
  if (tabId === 'reports') generateReport();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function toggleTheme() {
  const isDark = document.documentElement.classList.toggle('dark');
  const icon = $('theme-icon');
  if (icon) icon.textContent = isDark ? '☀️' : '🌙';
  try { localStorage.setItem('theme', isDark ? 'dark' : 'light'); } catch (_) { /* ignore */ }
}

(function applySavedTheme() {
  let saved = null;
  try { saved = localStorage.getItem('theme'); } catch (_) { /* ignore */ }
  if (saved === 'dark' || (!saved && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    document.documentElement.classList.add('dark');
    const icon = $('theme-icon');
    if (icon) icon.textContent = '☀️';
  }
})();

// ---------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  $('portal-live-date').textContent = new Date().toLocaleDateString('en-IN',
    { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
  $('attendance-date').value = currentDate;
  populateReportMonths();

  if (DEMO) {
    $('demo-banner').classList.remove('hidden');
    loadDemoData();
    afterDataLoaded();
    return;
  }

  showLogin();
  sb.auth.onAuthStateChange((event, session) => {
    // Defer so we don't call Supabase inside the auth callback (avoids deadlocks).
    setTimeout(() => {
      if (session?.user) {
        if (event === 'SIGNED_IN' || event === 'INITIAL_SESSION') onSignedIn(session.user);
      } else {
        me = null;
        showLogin();
      }
    }, 0);
  });
});
