const $ = (selector) => document.querySelector(selector)
const shell = $('.app-shell')
const state = { courses: [], activeJob: null, targets: [] }

function element(name, text, className = '') {
  const node = document.createElement(name)
  if (text !== undefined && text !== null) node.textContent = text
  if (className) node.className = className
  return node
}

function message(text = '', error = false) {
  const target = $('#liveMessage')
  if (!target) return
  target.textContent = text
  target.classList.toggle('is-error', error)
}

async function request(url, options = {}) {
  const response = await fetch(url, { headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options })
  let data = {}
  try { data = await response.json() } catch (_) { /* empty response */ }
  if (!response.ok) throw new Error(data.detail || response.statusText || 'Anfrage fehlgeschlagen')
  return data
}

function tokenConfigured() { return shell?.dataset.tokenConfigured === 'true' }
function selectedFolders() { return [...document.querySelectorAll('.course-checkbox:checked')].map((checkbox) => checkbox.value) }
function selectedTargetId() { return $('#targetSelect')?.value || state.targets[0]?.id || '' }
function statusClass(status) { return ['success', 'partial', 'failed', 'interrupted'].includes(status) ? status : '' }

function renderCourses() {
  const body = $('#courseRows')
  body.replaceChildren()
  if (!state.courses.length) {
    const row = element('tr'); const cell = element('td', 'Keine importierbaren Kursordner gefunden.', 'table-empty'); cell.colSpan = 7; row.append(cell); body.append(row); return
  }
  for (const course of state.courses) {
    const row = element('tr'); row.dataset.folder = course.folder_name
    const selectCell = element('td'); const checkbox = document.createElement('input')
    checkbox.type = 'checkbox'; checkbox.className = 'course-checkbox'; checkbox.value = course.folder_name; checkbox.setAttribute('aria-label', `${course.name} auswählen`)
    selectCell.append(checkbox); row.append(selectCell)
    const title = element('td'); const wrap = element('div', null, 'course-name')
    if (course.thumbnail) {
      const image = document.createElement('img'); image.className = 'course-thumb'; image.alt = ''; image.src = `/api/courses/${encodeURIComponent(course.folder_name)}/thumbnail`
      image.onerror = () => image.replaceWith(element('span', '▧', 'course-thumb-placeholder')); wrap.append(image)
    } else wrap.append(element('span', '▧', 'course-thumb-placeholder'))
    wrap.append(element('span', course.name)); title.append(wrap)
    row.append(title, element('td', course.chapter_count), element('td', course.lesson_count), element('td', course.size_human), element('td', course.library_path || '–'))
    const status = element('span', course.skipped_count ? `${course.skipped_count} übersprungen` : 'Bereit', `status-badge${course.skipped_count ? ' partial' : ' success'}`)
    const statusCell = element('td'); statusCell.append(status); row.append(statusCell); body.append(row)

    const detailRow = element('tr', null, 'course-details-row'); const detailCell = element('td', null, 'course-details-cell'); detailCell.colSpan = 7
    const detail = element('details', null, 'course-details'); detail.append(element('summary', `Kapitel anzeigen (${course.chapter_count})`))
    const chapters = element('div', null, 'chapter-list')
    for (const chapter of course.chapters) {
      const chapterNode = element('details', null, 'course-chapter'); const summary = element('summary')
      summary.append(element('strong', chapter.name), element('span', `${chapter.lesson_count} Lektionen`, 'chapter-count')); chapterNode.append(summary)
      const lessons = element('ol', null, 'chapter-lessons'); for (const lesson of chapter.lessons) lessons.append(element('li', lesson.title))
      chapterNode.append(lessons); chapters.append(chapterNode)
    }
    if (course.skipped_count) chapters.append(element('p', `${course.skipped_count} Datei(en) werden übersprungen: ${course.skipped.join(', ')}`, 'course-skipped'))
    detail.append(chapters); detailCell.append(detail); detailRow.append(detailCell); body.append(detailRow)
  }
}

async function scan() {
  const button = $('#scanButton'); button.disabled = true
  try { const data = await request('/api/scan'); state.courses = data.courses; renderCourses(); message(`${state.courses.length} Kursordner geprüft.`) }
  catch (error) { message(error.message, true) } finally { button.disabled = false }
}

function updateTargetDescription() {
  const target = state.targets.find((candidate) => candidate.id === selectedTargetId())
  $('#targetDescription').textContent = target ? `${target.url} · ${target.org_slug} · Organisations-ID ${target.org_id}` : 'Kein Ziel ausgewählt.'
}

async function loadTargets() {
  if (!tokenConfigured()) return
  try {
    const data = await request('/api/targets'); state.targets = data.targets || []
    const select = $('#targetSelect'); select.replaceChildren()
    for (const target of state.targets) { const option = element('option', target.label); option.value = target.id; select.append(option) }
    updateTargetDescription()
    $('#targetSummary').textContent = state.targets.length > 1 ? `${state.targets.length} lokale Ziele verfügbar` : state.targets.length === 1 ? `Ziel: ${state.targets[0].label}` : 'Kein Ziel konfiguriert'
  } catch (error) { message(error.message, true) }
}

function importPayload() {
  return { course_folders: selectedFolders(), target_id: selectedTargetId(), library_path: $('#libraryPath').value.trim(), publish: $('#publishCourses').checked, skip_duplicates: $('#skipDuplicates').checked }
}

async function beginImport() {
  const payload = importPayload(); const button = $('#importSelected')
  if (!payload.course_folders.length) { message('Wähle mindestens einen Kurs aus.', true); return }
  if (!payload.target_id) { message('Kein LearnHouse-Ziel konfiguriert.', true); return }
  button.disabled = true
  try {
    const data = await request('/api/import', { method: 'POST', body: JSON.stringify(payload) })
    state.activeJob = data.job_id; $('#jobPanel').classList.remove('hidden'); message('Import wurde gestartet.'); await refreshJob()
  } catch (error) { message(error.message, true) } finally { button.disabled = false }
}

function prepareImport() {
  if (!tokenConfigured()) { message('Hinterlege zuerst den API-Token in der lokalen Konfigurationsdatei.', true); return }
  if (!selectedFolders().length) { message('Wähle mindestens einen Kurs aus.', true); return }
  if (!state.targets.length) { message('Kein LearnHouse-Ziel konfiguriert.', true); return }
  if (state.targets.length === 1) { beginImport(); return }
  $('#targetCourseCount').textContent = String(selectedFolders().length); $('#targetDialog').showModal()
}

async function refreshJob() {
  if (!state.activeJob || !$('#jobPanel')) return
  try {
    const job = await request(`/api/jobs/${encodeURIComponent(state.activeJob)}`)
    $('#jobMessage').textContent = job.message; const badge = $('#jobStatus'); badge.textContent = job.status; badge.className = `status-badge ${statusClass(job.status)}`
    $('#progressBar').style.width = `${job.progress}%`; $('#progressValue').textContent = `${job.progress} %`; $('#jobLog').textContent = (job.log || []).join('\n')
    if (['queued', 'running'].includes(job.status)) setTimeout(refreshJob, 1200)
  } catch (error) { message(error.message, true) }
}

async function resume(jobId) {
  try {
    const data = await request(`/api/jobs/${encodeURIComponent(jobId)}/resume`, { method: 'POST' })
    window.location.assign(`/imports?job=${encodeURIComponent(data.job_id)}`)
  } catch (error) { message(error.message, true) }
}

async function refreshHistory() {
  try {
    const data = await request('/api/jobs'); const body = $('#historyRows'); body.replaceChildren()
    if (!data.jobs.length) { const row = element('tr'); const cell = element('td', 'Noch keine Importe.', 'table-empty'); cell.colSpan = 5; row.append(cell); body.append(row); return }
    for (const job of data.jobs) {
      const row = element('tr'); row.append(element('td', job.created_at || '–'))
      const status = element('td'); status.append(element('span', job.status, `status-badge ${statusClass(job.status)}`)); row.append(status)
      row.append(element('td', `${job.progress} %`), element('td', job.message || '–'))
      const action = element('td')
      if (['partial', 'failed', 'interrupted'].includes(job.status)) { const button = element('button', 'Fortsetzen', 'resume-button'); button.type = 'button'; button.addEventListener('click', () => resume(job.id)); action.append(button) }
      row.append(action); body.append(row)
    }
  } catch (error) { message(error.message, true) }
}

if (shell?.dataset.page === 'imports') {
  $('#scanButton').addEventListener('click', scan); $('#importSelected').addEventListener('click', prepareImport)
  $('#selectAll').addEventListener('change', (event) => document.querySelectorAll('.course-checkbox').forEach((box) => { box.checked = event.target.checked }))
  $('#targetSelect').addEventListener('change', updateTargetDescription)
  $('#confirmImport').addEventListener('click', () => { $('#targetDialog').close(); beginImport() })
  $('#connectionTest').addEventListener('click', async () => {
    if (!tokenConfigured()) { message('Kein API-Token konfiguriert.', true); return }
    try { const result = await request('/api/connection/test', { method: 'POST', body: JSON.stringify({ target_id: selectedTargetId() }) }); message(`Verbindung erfolgreich: ${result.organization.slug}`) }
    catch (error) { message(error.message, true) }
  })
  const jobId = new URLSearchParams(window.location.search).get('job')
  if (jobId) { state.activeJob = jobId; $('#jobPanel').classList.remove('hidden'); refreshJob() }
  scan(); loadTargets()
}

if (shell?.dataset.page === 'history') refreshHistory()
