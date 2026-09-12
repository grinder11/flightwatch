/* Plans tab. Reads docs/plans.json (built from plans.yaml by
   `analyze.py --json`) if it exists. There is no plans.yaml yet, by design --
   this tab is meant to start blank, so the empty state is a real design state
   rather than a broken page. */

const STATUS = {
  done:    {cls:'booked', label:'Done'},
  active:  {cls:'watch',  label:'In progress'},
  open:    {cls:'',       label:'Open'},
};

/* Shown when there is no plans.yaml. Sourced from PROJECT_PLAN.md's Phase 3 --
   the things already known to be coming, greyed out until they are real. */
const PLACEHOLDERS = [
  ['Hotels', 'Feb – Mar 2027', 'Tokyo, Kyoto, Osaka. Free-cancellation rates, re-checked in April.'],
  ['Sumo tickets', 'Apr 2027', 'Natsu basho at Ryōgoku. A weekday masu-seki box seats exactly four.'],
  ['Shinkansen', 'Apr 2027', 'Point-to-point on Smart EX. No JR Pass.'],
  ['eSIMs ×4', 'Apr 2027', 'Individual, not one shared pocket wifi.'],
  ['Yamato forwarding', 'May 2027', 'Hotel to hotel, arranged at the front desk.'],
];

function renderSections(doc){
  const sections = doc.sections || [];
  $('shell').innerHTML = sections.map(s => {
    const items = (s.items || []).map(i => {
      const st = STATUS[String(i.status || 'open').toLowerCase()] || STATUS.open;
      return `<li class="day">
        <div class="dstamp"><b>${esc(i.when || '')}</b></div>
        <div class="dbody">
          <h4>${esc(i.what || '')} <span class="pill ${st.cls}">${st.label}</span></h4>
          ${i.note ? `<p>${esc(i.note)}</p>` : ''}
        </div>
      </li>`;
    }).join('');
    return `<section>
      <h2>${esc(s.title || '')}</h2>
      ${s.note ? `<p class="lede">${esc(s.note)}</p>` : ''}
      <ol class="days">${items}</ol>
    </section>`;
  }).join('');

  const total = sections.reduce((a, s) => a + (s.items || []).length, 0);
  const done = sections.reduce((a, s) => a + (s.items || [])
    .filter(i => String(i.status).toLowerCase() === 'done').length, 0);
  $('stats').innerHTML = [
    ['Sections', sections.length],
    ['Items', total],
    ['Done', `${done} <span class="u">/ ${total}</span>`],
  ].map(([k, v]) =>
    `<div class="stat"><span class="k">${k}</span><span class="v">${v}</span></div>`
  ).join('');

  $('verdict').textContent = doc.title || 'Plans';
  $('sub').textContent = doc.note || '';
  $('stamp').textContent = doc.generated
    ? 'Built from plans.yaml on ' + new Date(doc.generated)
        .toLocaleString('en-US', {dateStyle:'medium', timeStyle:'short'}) + '.'
    : '';
}

function renderEmpty(){
  $('verdict').textContent = 'Nothing planned here yet.';
  $('sub').innerHTML = 'This tab is deliberately empty. The rows below are what '
    + 'is already known to be coming &mdash; they are not tracked until there is '
    + 'a <code>plans.yaml</code> to track them in.';
  $('stats').hidden = true;   // an empty grid still draws its border box
  $('shell').innerHTML = `
    <section>
      <p class="eyebrow">Known, not yet tracked</p>
      <ol class="days">${PLACEHOLDERS.map(([what, when, note]) => `
        <li class="day transit">
          <div class="dstamp"><b>${when}</b></div>
          <div class="dbody">
            <h4>${what} <span class="pill">Untracked</span></h4>
            <p>${note}</p>
          </div>
        </li>`).join('')}
      </ol>
    </section>
    <section>
      <div class="empty">
        <h3>To fill this tab in</h3>
        <p>Create <code>plans.yaml</code> in the repo root and run
        <code>python analyze.py --json</code>. The shape is free-form
        sections:</p>
        <pre style="overflow-x:auto; font-size:12px; line-height:1.5"><code>title: Plans
sections:
  - title: Hotels
    note: Free-cancellation rates only.
    items:
      - what: Tokyo, 5 nights
        when: Feb 2027
        status: open        # open | active | done
        note: Re-check the rate in April.</code></pre>
        <p>Anything you leave out is simply not rendered.</p>
      </div>
    </section>`;
}

loadJSON('plans.json').then(doc => {
  if(doc && (doc.sections || []).length) renderSections(doc);
  else renderEmpty();
});
