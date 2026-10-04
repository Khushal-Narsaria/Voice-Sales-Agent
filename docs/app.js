'use strict';

const LANGS = { en: 'English', hinglish: 'Hinglish', hi: 'Hindi' };
const VARIANT = { zero_shot: 'Zero-shot', few_shot: 'Few-shot', persona: 'Few-shot + persona & voice rules' };
const FLOW = { code_flow: 'flow engine in code', llm_flow: 'LLM runs the flow' };
const cfgName = c => `${VARIANT[c.variant]} · ${c.model} · ${FLOW[c.flow_mode]}`;
const pctCol = (label, key) => ({ label, key, num: true, format: v => v == null ? '–' : F.pct(v) });

const TABS = {
  Overview(D) {
    const b = D.summary[D.best];
    return section(
      intro('Priya calls home-loan leads who left their number on a (fictional) lender\'s website. She talks in English, Hinglish or Hindi, collects the six facts an advisor needs, handles rate questions and refusals, and books a free advisor call. Every number below comes from simulated calls with 26 held-out customer personas.'),
      tiles([
        ['Calls ending the right way', F.pct0(b.task_success), `booked, callback, refusal respected… (${b.calls} calls)`],
        ['Facts captured correctly', F.pct0(b.field_accuracy), 'city, property, loan, job, income, slot'],
        ['Replies in the customer\'s language', F.pct0(b.lang_match), 'English, Hinglish or Hindi script'],
        ['Policy breaks spoken', String(b.violations), `${b.violations_before_guard} caught by the guard before speaking`],
      ]),
      grid(
        card({ title: 'How one turn works', wide: true }, null),
        card({ title: 'What is measured', sub: 'Success metrics per call, scored against each persona\'s ground truth' }, null),
        card({ title: 'Test set', sub: '26 personas, never used while tuning prompts (8 separate dev personas were)' }, null),
      ),
    ).also(sec => {
      const [how, what, set] = sec.querySelectorAll('figure');
      how.append(h('ol', { class: 'steps' }, [
        ['Speech to text', ' — Whisper (small, int8 on CPU) transcribes the customer; language is detected automatically.'],
        ['Understand', ' — a local open-source LLM (qwen2.5:3b) returns JSON: intent, the fields the customer gave, the exact words each field came from, and a short reply.'],
        ['Check in code', ' — the flow engine keeps a field only if the quote really occurs in what was said, reads Indian amounts itself ("1.5 crore", "पचास हज़ार"), checks a slot has a day or time, and applies business rules (income below ₹25k a month is not eligible).'],
        ['Decide in code', ' — the engine moves the call (greet → discover → qualify → book, or callback) and picks the next question from a script in the customer\'s language.'],
        ['Guard and speak', ' — replies are cleaned for speech, rate/approval promises and OTP requests are replaced by a safe line, endings use fixed closings, then text to speech.'],
      ].map(([b2, t]) => h('li', {}, h('b', { text: b2 }), t))));
      what.append(h('ul', { class: 'note-list' }, [
        'Task success: the call ended with the outcome the business wanted for that customer.',
        'Field accuracy: share of the persona\'s facts captured with the right value.',
        'Spoken violations: interest-rate or approval promises, or asking for an OTP/PIN/ID number.',
        'Voice style: at most 35 words and 3 sentences, no markdown, emojis, links or "₹50,00,000".',
        'Language match: Hindi gets Devanagari; Hinglish gets Hinglish or English; English gets English.',
      ].map(t => h('li', { text: t }))));
      const by = {};
      for (const c of D.calls.filter(c => c.config === D.best)) (by[c.behavior] ??= new Set()).add(c.language);
      set.append(dataTable([{ label: 'Customer behaviour', key: 'b' }, { label: 'Languages', key: 'l' }],
        Object.entries(by).map(([b2, ls]) => ({ b: b2.replace('_', ' '), l: [...ls].map(l => LANGS[l]).join(', ') }))));
    });
  },

  Prompts(D) {
    const rows = D.order.map(k => ({ name: cfgName(D.summary[k]), key: k, ...D.summary[k] }));
    const variants = D.order.filter(k => D.summary[k].model === 'qwen2.5:3b' && D.summary[k].flow_mode === 'code_flow');
    const series = [{ name: 'Task success', color: C.actual }, { name: 'Field accuracy', color: C.model }];
    return section(
      intro('The same model (qwen2.5:3b) with three prompts that build on each other, then the same best prompt with the model running the whole flow itself, then two other open models. The customer simulator is the same for every row.'),
      grid(
        card({ title: 'Prompt variants', sub: 'qwen2.5:3b, flow engine in code', legend: series.map(s2 => ({ ...s2, shape: 'box' })),
          table: { columns: [{ label: 'Prompt', key: 'name' }, pctCol('Task success', 'task_success'), pctCol('Fields', 'field_accuracy')], rows: rows.filter(r => variants.includes(r.key)) } },
        plot => hbars(plot, { rows: variants.map(k => ({ label: VARIANT[D.summary[k].variant], values: [D.summary[k].task_success, D.summary[k].field_accuracy] })), series, format: F.pct0, max: 1 })),
        card({ title: 'Who owns the flow?', sub: 'Best prompt, qwen2.5:3b', legend: series.map(s2 => ({ ...s2, shape: 'box' })) },
          plot => hbars(plot, { rows: D.order.filter(k => D.summary[k].model === 'qwen2.5:3b' && D.summary[k].variant === 'persona').map(k => ({ label: FLOW[D.summary[k].flow_mode], values: [D.summary[k].task_success, D.summary[k].field_accuracy] })), series, format: F.pct0, max: 1 })),
        card({ title: 'All configurations', wide: true, table: { columns: [
          { label: 'Configuration', key: 'name' }, pctCol('Task success', 'task_success'), pctCol('Fields', 'field_accuracy'),
          { label: 'Spoken violations', key: 'violations', num: true }, { label: 'Before guard', key: 'violations_before_guard', num: true },
          pctCol('Voice style', 'style_ok'), pctCol('Language', 'lang_match'), pctCol('Valid JSON', 'json_ok'),
          { label: 'Turns', key: 'avg_turns', num: true, format: v => v.toFixed(1) }, { label: 'Words / reply', key: 'reply_words', num: true, format: v => v.toFixed(1) },
          { label: 'p50 ms', key: 'latency_p50_ms', num: true, format: F.int }, { label: 'p95 ms', key: 'latency_p95_ms', num: true, format: F.int }],
          rows, best: r => r.key === D.best } }, null),
      ),
    );
  },

  Calls(D) {
    const cfgSel = h('select', { 'aria-label': 'Configuration' }, D.order.map(k => h('option', { value: k, text: cfgName(D.summary[k]), selected: k === D.best })));
    const personas = [...new Set(D.calls.map(c => c.persona))];
    const pSel = h('select', { 'aria-label': 'Customer' }, personas.map(p => {
      const c = D.calls.find(x => x.persona === p);
      return h('option', { value: p, text: `${p} · ${LANGS[c.language]} · ${c.behavior.replace('_', ' ')}` });
    }));
    const body = h('div', {});
    function draw() {
      const c = D.calls.find(x => x.config === cfgSel.value && x.persona === pSel.value);
      const audio = D.audio[`${c.config}|${c.persona}`];
      const lines = [h('div', { class: 'bubble agent' }, h('span', { class: 'who', text: 'Priya' }), c.opening)];
      c.turns.forEach((t, i) => {
        lines.push(h('div', { class: 'bubble customer' }, h('span', { class: 'who', text: 'Customer (simulated)' }), t.customer));
        const tags = [h('span', { class: 'tag', text: t.intent }), h('span', { class: 'tag', text: 'stage: ' + t.state })];
        if (t.guard.length) tags.push(h('span', { class: 'tag flag', text: 'guard: ' + t.guard.join(', ') }));
        if (t.lang_retry) tags.push(h('span', { class: 'tag flag', text: 'language rewrite' }));
        if (t.style_issues.length) tags.push(h('span', { class: 'tag flag', text: t.style_issues.join(', ') }));
        lines.push(h('div', { class: 'bubble agent' }, h('span', { class: 'who', text: 'Priya' }), t.reply,
          audio && audio[i] ? h('audio', { controls: true, preload: 'none', src: audio[i] }) : null, h('div', { class: 'tags' }, tags)));
      });
      const ok = c.outcome === c.expected;
      body.replaceChildren(
        h('p', { class: 'outcome' }, h('span', { class: 'status' + (ok ? '' : ' miss'), text: ok ? 'Right outcome' : 'Wrong outcome' }),
          ` — ended as "${c.outcome.replace('_', ' ')}", wanted "${c.expected.replace('_', ' ')}". Fields correct: ${c.field_accuracy == null ? 'n/a' : F.pct0(c.field_accuracy)}.`),
        audio ? h('p', { class: 'sub', text: 'Agent replies have audio (gTTS) for this call.' }) : null,
        h('div', { class: 'call' }, lines),
        h('p', { class: 'sub', style: 'margin-top:12px', text: 'Collected: ' + JSON.stringify(c.slots) }));
    }
    cfgSel.addEventListener('change', draw);
    pSel.addEventListener('change', draw);
    const firstAudio = Object.keys(D.audio)[0];
    if (firstAudio) pSel.value = firstAudio.split('|')[1];
    const sec = section(intro('Every simulated call, turn by turn: what the customer said, the intent the agent understood, the stage of the flow and any guardrail that fired. Calls with audio play the agent\'s spoken replies.'),
      h('div', { class: 'control' }, 'Configuration', cfgSel, 'Customer', pSel), body);
    draw();
    return sec;
  },

  Voice(D) {
    const V = D.voice;
    if (!V) return section(intro('Voice results not generated yet.'));
    const snrs = ['clean', '20', '10', '5'];
    const label = s2 => s2 === 'clean' ? 'Clean' : `${s2} dB`;
    const series = Object.keys(LANGS).map((l, i) => ({ name: LANGS[l], color: [C.actual, C.model, C.baseline][i] }));
    return section(
      intro('36 customer answers (12 per language) were synthesized, mixed with call-centre babble at falling signal-to-noise ratios, transcribed by Whisper and passed to the agent. Left to detect the language itself, Whisper often hears Hindi as Urdu and writes Urdu script. Telling it the call language lowers the Hindi word error rate under noise, but the facts captured barely change: Whisper small\'s Hindi accuracy is the bottleneck, not the agent.'),
      tiles([
        ['Fact captured from typed text', F.pct0(V.summary.field_ok_from_text), 'same agent, no speech step'],
        ['Fact captured from clean audio', `${F.pct0(V.summary.by_snr.clean.field_ok_from_audio)} → ${F.pct0(V.summary.by_snr.clean.field_ok_from_audio_locked)}`, 'auto-detect → language locked'],
        ['Fact captured at 5 dB', `${F.pct0(V.summary.by_snr['5'].field_ok_from_audio)} → ${F.pct0(V.summary.by_snr['5'].field_ok_from_audio_locked)}`, 'noise almost as loud as speech'],
        ['Whisper real-time factor', V.summary.real_time_factor_median.toFixed(2), `median ${V.summary.stt_seconds_median}s for ${V.summary.audio_seconds_median}s of audio`],
      ]),
      grid(
        card({ title: 'Fact captured from audio: auto-detect vs language locked', sub: 'Share of the 12 utterances per language. Locked = Whisper is told the call language (Hindi for Hindi and Hinglish callers).',
          legend: [{ name: 'Whisper detects the language', color: C.actual, shape: 'box' }, { name: 'Language locked from the call', color: C.model, shape: 'box' }], wide: true,
          table: { columns: [{ label: 'Language', key: 'l' }, { label: 'Whisper', key: 'm' }, pctCol('Typed text', 't'), ...snrs.map(s2 => pctCol(label(s2), s2))],
            rows: Object.keys(LANGS).flatMap(l => [
              { l: LANGS[l], m: 'auto-detect', t: V.summary.by_language[l].field_ok_from_text, ...Object.fromEntries(snrs.map(s2 => [s2, V.summary.by_language[l]['field_ok_from_audio_' + s2]])) },
              { l: LANGS[l], m: 'language locked', ...Object.fromEntries(snrs.map(s2 => [s2, V.summary.by_language[l]['field_ok_locked_' + s2]])) }]) } },
          plot => hbars(plot, { rows: Object.keys(LANGS).flatMap(l => ['clean', '5'].map(s2 => ({ label: `${LANGS[l]} · ${label(s2)}`,
            values: [V.summary.by_language[l]['field_ok_from_audio_' + s2], V.summary.by_language[l]['field_ok_locked_' + s2]] }))),
            series: [{ name: 'Auto-detect', color: C.actual }, { name: 'Locked', color: C.model }], format: F.pct0, max: 1 })),
        card({ title: 'Word error rate', sub: 'English and Hindi (same script in reference and transcript)', legend: [{ name: 'English', color: C.actual, shape: 'box' }, { name: 'Hindi', color: C.model, shape: 'box' }] },
          plot => hbars(plot, { rows: snrs.map(s2 => ({ label: label(s2), values: [V.summary.by_snr[s2].wer_en, V.summary.by_snr[s2].wer_hi] })), series: [{ name: 'English', color: C.actual }, { name: 'Hindi', color: C.model }], format: F.pct0 })),
        card({ title: 'Hear the noise', sub: 'The same Hindi answer at 20, 10 and 5 dB', wide: true }, null),
        card({ title: 'Transcripts', wide: true, table: { columns: [{ label: 'Id', key: 'id' }, { label: 'Noise', key: 'snr' }, { label: 'Said', key: 'text' }, { label: 'Whisper heard', key: 'transcript' },
          { label: 'Fact (auto)', key: 'field_ok_from_audio', render: v => h('span', { class: 'status' + (v ? '' : ' miss'), text: v ? 'yes' : 'no' }) },
          { label: 'Heard (locked)', key: 'transcript_locked' },
          { label: 'Fact (locked)', key: 'field_ok_from_audio_locked', render: v => h('span', { class: 'status' + (v ? '' : ' miss'), text: v ? 'yes' : 'no' }) }], rows: V.rows } }, null),
      ),
    ).also(sec => {
      const hear = sec.querySelectorAll('figure')[2];
      hear.append(...['20', '10', '5'].map(s2 => h('div', {}, h('p', { class: 'sub', text: `${s2} dB` }), h('audio', { controls: true, preload: 'none', src: `audio/noise/hi-1_${s2}db.wav` }))));
    });
  },

  'SQL analytics'(D) {
    const A = D.analytics;
    const cards = Object.entries(A.results).filter(([k]) => k !== '_end').map(([name, t]) => {
      const cols = t.columns.map(c => ({ label: c, key: c, num: typeof t.rows[0]?.[t.columns.indexOf(c)] === 'number' }));
      const rows = t.rows.map(r => Object.fromEntries(t.columns.map((c, i) => [c, r[i]])));
      const fig = card({ title: name.replace(/_/g, ' '), wide: true, table: { columns: cols, rows } }, null);
      fig.querySelector('.card-head').after(h('pre', { class: 'sql', text: A.sql[name] || '' }));
      return fig;
    });
    return section(intro('Every call and turn is loaded into SQLite (calls, turns, violations, field events). These are the queries a voicebot team would run on real conversational data; the results come from the same simulated calls.'), grid(...cards));
  },

  Iterations(D) {
    return section(intro('How the prompts and the flow were improved, measured on 8 development personas only (the 26 test personas were never used while tuning).'),
      grid(card({ title: 'Iteration log', wide: true, table: { columns: [{ label: '#', key: 'n' }, { label: 'Change', key: 'change' }, { label: 'Problem it fixed', key: 'problem' }, { label: 'Dev-set result', key: 'result' }], rows: D.iterations } }, null)));
  },
};

HTMLElement.prototype.also = function (fn) { fn(this); return this; };

(async function main() {
  const D = await (await fetch('data.json')).json();
  document.getElementById('lede').textContent =
    `A voice AI sales agent that qualifies home-loan leads in English, Hinglish and Hindi: a conversation flow engine, prompt variants, compliance guardrails, ${D.calls.length} simulated calls, Whisper speech tests under noise and SQL analytics. Open-source models only, running on a laptop.`;
  document.getElementById('src').href = D.repo;
  document.getElementById('foot').textContent = `Built by ${D.author}. Personas and the lender ("Ghar Home Loans") are fictional.`;
  const mainEl = document.getElementById('main'), nav = document.getElementById('tabs');
  const names = Object.keys(TABS), built = {};
  const slug = n => n.toLowerCase().replace(/\s+/g, '-');
  function open(name) {
    hideTip();
    for (const b of nav.children) b.setAttribute('aria-selected', String(b.textContent === name));
    for (const el of mainEl.children) el.hidden = true;
    built[name] ??= mainEl.appendChild(TABS[name](D));
    built[name].hidden = false;
    history.replaceState(null, '', '#' + slug(name));
    renderAll();
  }
  nav.append(...names.map(n => h('button', { type: 'button', role: 'tab', text: n, onclick: () => open(n) })));
  open(names.find(n => '#' + slug(n) === location.hash) || names[0]);
  let timer;
  addEventListener('resize', () => { clearTimeout(timer); timer = setTimeout(renderAll, 150); });
  const btn = document.getElementById('theme');
  const dark = () => (document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')) === 'dark';
  btn.textContent = dark() ? 'Light mode' : 'Dark mode';
  btn.addEventListener('click', () => { document.documentElement.dataset.theme = dark() ? 'light' : 'dark'; btn.textContent = dark() ? 'Light mode' : 'Dark mode'; });
})();
