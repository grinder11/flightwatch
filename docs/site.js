/* Shared helpers for every tab. Loaded before each page's own script.
   The nav's active tab is marked with aria-current in each page's HTML,
   not here, so it survives with JS disabled. */

const $ = id => document.getElementById(id);
const usd = n => '$' + Math.round(n).toLocaleString('en-US');

/* YAML-authored content lands in innerHTML, so escape it -- a stray & or <
   in a note should render, not break the markup. */
const esc = s => String(s ?? '').replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function fmtDuration(min){
  if(min == null) return '?';
  const h = Math.floor(min/60), m = min%60;
  return `${h}h ${String(m).padStart(2,'0')}m`;
}

function fmtClock(raw){
  // raw: "YYYY-MM-DD HH:MM", local to that airport -- not UTC, not
  // necessarily the same timezone as the other end of the leg.
  const [, time] = raw.split(' ');
  const [h, m] = time.split(':').map(Number);
  const ampm = h >= 12 ? 'PM' : 'AM';
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2,'0')} ${ampm}`;
}

function dayOffset(depRaw, arrRaw){
  const d0 = new Date(depRaw.split(' ')[0]), d1 = new Date(arrRaw.split(' ')[0]);
  return Math.round((d1 - d0) / 86400000);
}

function stopsText(n){
  if(n == null) return '?';
  return n === 0 ? 'Nonstop' : n === 1 ? '1 stop' : `${n} stops`;
}

/* "2027-05-15" -> {dow:"Sat", day:"15 May"}. Parsed as UTC on purpose:
   a bare date string is a calendar date, and local-midnight parsing can
   shift it a day west of UTC. */
function fmtDay(iso){
  const d = new Date(iso + 'T00:00:00Z');
  if(isNaN(d)) return {dow:'', day:iso};
  return {
    dow: d.toLocaleDateString('en-US', {weekday:'short', timeZone:'UTC'}),
    day: d.toLocaleDateString('en-US', {day:'numeric', month:'short', timeZone:'UTC'}),
  };
}

/* Resolves to null rather than throwing, so a missing payload is a state
   the page renders instead of an error it dies on. */
function loadJSON(path){
  return fetch(path, {cache:'no-store'})
    .then(r => r.ok ? r.json() : null)
    .catch(() => null);
}

/* Shown when a page is opened over file://, where fetch is blocked. */
const SERVE_HINT = 'If you opened this file directly, serve it instead: '
  + '<code>cd docs &amp;&amp; python3 -m http.server 8000</code>';
