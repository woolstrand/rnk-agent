(() => {
  const STEP_POLL_MS = 1500;

  const stepListEl = document.getElementById('stepList');
  const followBtn = document.getElementById('followBtn');
  const followState = document.getElementById('followState');
  const emptyState = document.getElementById('emptyState');
  const mainTab = document.getElementById('mainTab');
  const debugTab = document.getElementById('debugTab');
  const tabBtns = document.querySelectorAll('.tab-btn');

  const prevFrame = document.getElementById('prevFrame');
  const currentFrame = document.getElementById('currentFrame');
  const prevFrameOffline = document.getElementById('prevFrameOffline');
  const currentFrameOffline = document.getElementById('currentFrameOffline');
  const llmErrorEl = document.getElementById('llmError');
  const parseErrorEl = document.getElementById('parseError');
  const audioOfflineEl = document.getElementById('audioOffline');
  const heardList = document.getElementById('heardList');
  const todoList = document.getElementById('todoList');
  const obsList = document.getElementById('obsList');
  const thoughtsEl = document.getElementById('thoughts');
  const reasoningEl = document.getElementById('reasoning');
  const commandsList = document.getElementById('commandsList');
  const systemPromptEl = document.getElementById('systemPrompt');
  const userTextEl = document.getElementById('userText');
  const rawReplyEl = document.getElementById('rawReply');
  const llmReasoningEl = document.getElementById('llmReasoning');

  let steps = [];
  let selectedIteration = null; // null = follow latest
  let loadedIteration = null;

  async function api(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error(`Request failed (${res.status})`);
    return res.json();
  }

  function updateFollowBadge() {
    const following = selectedIteration === null;
    followState.textContent = following ? 'following latest' : `viewing step ${selectedIteration}`;
    followState.className = `badge ${following ? 'badge-ok' : 'badge-unknown'}`;
    followBtn.disabled = following;
  }

  function renderStepList() {
    stepListEl.innerHTML = '';
    for (const step of steps) {
      const li = document.createElement('li');
      li.className = 'step-item';
      if (step.iteration === selectedIteration) li.classList.add('selected');
      if (selectedIteration === null && step === steps[steps.length - 1]) li.classList.add('selected');
      const time = step.timestamp ? step.timestamp.split('T')[1] || step.timestamp : '';
      li.textContent = `Step ${step.iteration} — ${time}`;
      li.addEventListener('click', () => selectStep(step.iteration));
      stepListEl.appendChild(li);
    }
    if (selectedIteration === null) {
      stepListEl.scrollTop = stepListEl.scrollHeight;
    }
  }

  function selectStep(iteration) {
    selectedIteration = iteration;
    updateFollowBadge();
    renderStepList();
    loadStepDetail(iteration);
  }

  followBtn.addEventListener('click', () => {
    selectedIteration = null;
    updateFollowBadge();
    renderStepList();
    if (steps.length) loadStepDetail(steps[steps.length - 1].iteration);
  });

  tabBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      tabBtns.forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      const tab = btn.dataset.tab;
      mainTab.classList.toggle('hidden', tab !== 'main');
      debugTab.classList.toggle('hidden', tab !== 'debug');
    });
  });

  function renderList(el, items, render) {
    el.innerHTML = '';
    if (!items || !items.length) {
      const li = document.createElement('li');
      li.className = 'muted';
      li.textContent = '(none)';
      el.appendChild(li);
      return;
    }
    for (const item of items) {
      const li = document.createElement('li');
      render(li, item);
      el.appendChild(li);
    }
  }

  function setFrame(imgEl, offlineEl, relpath) {
    imgEl.src = relpath ? `/api/frames/${relpath}` : '';
    imgEl.classList.toggle('hidden', !relpath);
    offlineEl.classList.toggle('hidden', !!relpath);
  }

  function renderDetail(detail) {
    emptyState.classList.add('hidden');
    mainTab.classList.remove('hidden');

    setFrame(prevFrame, prevFrameOffline, detail.prev_frame);
    setFrame(currentFrame, currentFrameOffline, detail.current_frame);

    llmErrorEl.textContent = detail.llm_error ? `LLM error: ${detail.llm_error}` : '';
    llmErrorEl.classList.toggle('hidden', !detail.llm_error);
    parseErrorEl.textContent = detail.parse_error ? `Parse error: ${detail.parse_error}` : '';
    parseErrorEl.classList.toggle('hidden', !detail.parse_error);

    audioOfflineEl.classList.toggle('hidden', detail.audio_connected !== false);
    renderList(heardList, detail.heard_messages, (li, msg) => {
      li.textContent = msg;
    });

    renderList(todoList, detail.todo, (li, item) => {
      li.textContent = `[${item.checked ? 'x' : ' '}] ${item.text}`;
    });

    renderList(obsList, detail.observations, (li, entry) => {
      li.innerHTML = `<strong>${entry.name}</strong> <span class="muted">(updated ${entry.updated_at})</span><br>${entry.text}`;
    });

    thoughtsEl.textContent = detail.thoughts || '(none)';
    reasoningEl.textContent = detail.reasoning || '(none)';

    renderList(commandsList, detail.commands, (li, cmd) => {
      const status = cmd.status || 'unknown';
      li.className = `command command-${status}`;
      const params = cmd.params ? JSON.stringify(cmd.params) : '{}';
      const outcome = cmd.error ? `error: ${cmd.error}` : cmd.result ? JSON.stringify(cmd.result) : '';
      li.innerHTML = `<span class="command-status">${status}</span> <strong>${cmd.action}</strong> ${params} <span class="muted">${outcome}</span>`;
    });

    systemPromptEl.textContent = detail.system_prompt || '';
    userTextEl.textContent = detail.user_text || '';
    rawReplyEl.textContent = detail.raw_reply || '(none)';
    llmReasoningEl.textContent = detail.llm_reasoning || '(none)';
  }

  async function loadStepDetail(iteration) {
    if (iteration === loadedIteration) return;
    try {
      const detail = await api(`/api/steps/${iteration}`);
      loadedIteration = iteration;
      renderDetail(detail);
    } catch (err) {
      // step file may not exist yet if this iteration is mid-write - try again next poll
    }
  }

  async function pollSteps() {
    try {
      steps = await api('/api/steps');
    } catch (err) {
      return;
    }
    renderStepList();
    if (selectedIteration === null && steps.length) {
      await loadStepDetail(steps[steps.length - 1].iteration);
    }
  }

  updateFollowBadge();
  pollSteps();
  setInterval(pollSteps, STEP_POLL_MS);
})();
