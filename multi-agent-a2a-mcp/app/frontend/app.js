const form = document.getElementById('create-form');
const pathContainer = document.getElementById('path-container');
const pathContent = document.getElementById('path-content');
const progressContainer = document.getElementById('progress-container');
const statusText = document.getElementById('status-text');
const topic = document.getElementById('topic-input');
const feedback = document.getElementById('feedback-input');
let task = null;

function requestId() { return crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`; }
async function post(url, payload) {
    const response = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
    if (!response.ok) throw new Error('Your course session could not continue.');
    return response.json();
}
function showPath(payload) {
    task = payload;
    const path = payload.learning_path;
    pathContent.replaceChildren();
    [['Learner goal', path.goal], ['Assumed level', path.assumptions.join(' ')], ['Gaps to cover', path.knowledge_gaps.join(', ') || 'None identified.']].forEach(([title, value]) => {
        const section = document.createElement('p');
        const label = document.createElement('strong');
        label.textContent = `${title}: `;
        section.append(label, document.createTextNode(value));
        pathContent.appendChild(section);
    });
    const modules = document.createElement('ol');
    path.modules.forEach(module => {
        const item = document.createElement('li');
        item.textContent = `${module.title}: ${module.outcome}`;
        modules.appendChild(item);
    });
    pathContent.appendChild(modules);
    if (path.caveats.length) {
        const caveat = document.createElement('p');
        caveat.textContent = `Judge notes: ${path.caveats.join(' ')}`;
        pathContent.appendChild(caveat);
    }
    form.classList.add('hidden');
    pathContainer.classList.remove('hidden');
    document.getElementById('approve-button').focus();
}
form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    try {
        task = await post('/api/learner/start', {subject: topic.value.trim()});
        form.classList.add('hidden'); progressContainer.classList.remove('hidden');
        statusText.textContent = 'Researching and fact-checking your learning path…';
        watchCourse(task.task_id);
    } catch (error) { statusText.textContent = error.message; progressContainer.classList.remove('hidden'); }
});
async function continueWorkflow(action, response = '') {
    const result = await post('/api/learner/continue', {task_id: task.task_id, context_id: task.context_id, action, response, idempotency_key: requestId()});
    pathContainer.classList.add('hidden'); progressContainer.classList.remove('hidden');
    statusText.textContent = action === 'feedback' ? 'Revising and fact-checking your learning path…' : 'Writing your course…';
    watchCourse(result.task_id);
}
document.getElementById('approve-button').addEventListener('click', () => continueWorkflow('approve').catch(error => { statusText.textContent = error.message; progressContainer.classList.remove('hidden'); }));
document.getElementById('feedback-button').addEventListener('click', () => {
    const text = feedback.value.trim();
    if (!text) return feedback.focus();
    continueWorkflow('feedback', text).catch(error => { statusText.textContent = error.message; progressContainer.classList.remove('hidden'); });
});
function watchCourse(taskId) {
    const labels = {researching: 'Researching your learning path…', 'fact-checking': 'Fact-checking the research…', writing: 'Writing your course…'};
    const poll = async () => {
        try {
            const response = await fetch(`/api/learner/${encodeURIComponent(taskId)}`);
            if (!response.ok) throw new Error('Your course session could not continue.');
            const taskStatus = await response.json();
            if (taskStatus.phase === 'input_required' && taskStatus.learning_path) {
                progressContainer.classList.add('hidden'); feedback.value = ''; showPath(taskStatus); return;
            }
            statusText.textContent = labels[taskStatus.stage] || 'Preparing your course…';
            if (taskStatus.phase === 'completed' && taskStatus.course) { localStorage.setItem('currentCourse', taskStatus.course); window.location.href = '/course.html'; return; }
            if (taskStatus.phase === 'retryable_failed') throw new Error('Course generation failed. Please start again.');
            window.setTimeout(poll, 1000);
        } catch (error) { statusText.textContent = error.message; }
    };
    poll();
}
