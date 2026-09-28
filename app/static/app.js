const $ = (selector) => document.querySelector(selector)
const state = { courses: [], selected: null, activeJob: null, targets: [] }

function element(name, text, className = '') {
  const node = document.createElement(name)
  if (text !== undefined && text !== null) node.textContent = text
  if (className) node.className = className
  return node
}

function message(text = '', error = false) {
  const target = $('#liveMessage')
  target.textContent = text
  target.classList.toggle('is-error', error)
}

async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  let data = {}
  try { data = await response.json() } catch (_) { /* empty response */ }
  if (!response.ok) throw new Error(data.detail || response.statusText || 'Anfrage fehlgeschlagen')
  return data
}

function tokenConfigured() {
  return $('.app-shell').dataset.tokenConfigured === 'true'
}

function renderCourses() {
  const body = $('#courseRows')
  body.replaceChildren()
  if (!state.courses.length) {
    body.append(element('tr')).append(element('td', 'Keine importierbaren Kursordner gefunden.', 'table-empty'))
    body.firstChild.firstChild.colSpan = 7
    return
  }
  for (const course of state.courses) {
    const row = element('tr', null, state.selected?.folder_name === course.folder_name ? 'is-selected' : '')
    row.dataset.folder = course.folder_name
    const selectCell = element('td')
    const checkbox = document.createElement('input')
    checkbox.type = 'checkbox'
    checkbox.className = 'course-checkbox'
    checkbox.value = course.folder_name
    checkbox.setAttribute('aria-label', `${course.name} auswählen`)
    selectCell.append(checkbox)
    row.append(selectCell)
    const title = element('td')
    const wrap = element('div', null, 'course-name')
    if (course.thumbnail) {
      const image = document.createElement('img')
      image.className = 'course-thumb'
      image.alt = ''
      image.src = `/api/courses/${encodeURIComponent(course.folder_name)}/thumbnail`
      image.onerror = () => image.replaceWith(element('span', '▧', 'course-thumb-placeholder'))
      wrap.append(image)
    } else {
      wrap.append(element('span', '▧', 'course-thumb-placeholder'))
    }
    wrap.append(element('span', course.name))
    title.append(wrap)
    row.append(title, element('td', course.chapter_count), element('td', course.lesson_count), element('td', course.size_human), element('td', course.library_path || '–'))
    const status = element('span', course.skipped_count ? `${course.skipped_count} übersprungen` : 'Bereit', `status-badge${course.skipped_count ? ' partial' : ' success'}`)
    const statusCell = element('td'); statusCell.append(status); row.append(statusCell)
    row.addEventListener('click', (event) => {
      if (event.target.closest('input')) return
      state.selected = course
      renderCourses(); renderPreview(course)
    })
    body.append(row)
  }
}

function renderPreview(course) {
  const preview = $('#preview')
  preview.replaceChildren()
  if (!course) {
    preview.append(element('h2', 'Kurs auswählen'), element('p', 'Wähle links einen Kurs, um seine Kapitel, Lektionen und übersprungenen Dateien zu prüfen.'))
    return
  }
  preview.append(element('h2', course.name))
  const meta = element('div', null, 'preview-meta')
  meta.append(element('span', `${course.chapter_count} Kapitel`), element('span', `${course.lesson_count} Lektionen`), element('span', course.size_human))
  preview.append(meta)
  if (course.library_path) preview.append(element('p', `Library: ${course.library_path}`))
  const tree = element('div', null, 'preview-tree')
  for (const chapter of course.chapters) {
    const chapterNode = element('div', null, 'preview-chapter')
    chapterNode.append(element('strong', `${chapter.name} (${chapter.lesson_count})`))
    const lessons = element('ul', null, 'preview-lessons')
    for (const lesson of chapter.lessons.slice(0, 6)) lessons.append(element('li', lesson.title))
    if (chapter.lesson_count > 6) lessons.append(element('li', `… ${chapter.lesson_count - 6} weitere Lektionen`))
    chapterNode.append(lessons); tree.append(chapterNode)
  }
  preview.append(tree)
  if (course.skipped_count) {
    const skipped = element('div', null, 'preview-skipped')
    skipped.append(element('strong', `Übersprungen (${course.skipped_count})`))
    const list = element('ul')
    for (const file of course.skipped.slice(0, 8)) list.append(element('li', file))
    skipped.append(list); preview.append(skipped)
  }
}

async function scan() {
  $('#scanButton').disabled = true
  try {
    const data = await request('/api/scan')
    state.courses = data.courses
    if (!state.courses.some((course) => course.folder_name === state.selected?.folder_name)) state.selected = state.courses[0] || null
    renderCourses(); renderPreview(state.selected)
    $('#readyCount').textContent = state.courses.length
    message(`${state.courses.length} Kursordner geprüft.`)
  } catch (error) { message(error.message, true) }
  finally { $('#scanButton').disabled = false }
}

function selectedFolders() {
  return [...document.querySelectorAll('.course-checkbox:checked')].map((checkbox) => checkbox.value)
}

function selectedTargetId() {
  return $('#targetSelect')?.value || state.targets[0]?.id || ''
}

async function loadTargets() {
  if (!tokenConfigured()) return
  try {
    const data = await request('/api/targets')
    state.targets = data.targets || []
    const select = $('#targetSelect')
    select.replaceChildren()
    for (const target of state.targets) {
      const option = element('option', target.label)
      option.value = target.id
      option.dataset.org = `${target.org_slug} · ID ${target.org_id}`
      select.append(option)
    }
    updateTargetDescription()
    $('#targetSummary').textContent = state.targets.length > 1
      ? `${state.targets.length} lokale Ziele verfügbar`
      : state.targets.length === 1 ? `Ziel: ${state.targets[0].label}` : 'Kein Ziel konfiguriert'
  } catch (error) { message(error.message, true) }
}

function updateTargetDescription() {
  const target = state.targets.find((candidate) => candidate.id === selectedTargetId())
  $('#targetDescription').textContent = target
    ? `${target.org_slug} · Organisations-ID ${target.org_id}`
    : 'Kein Ziel ausgewählt.'
}

function importPayload() {
  return {
    course_folders: selectedFolders(),
    target_id: selectedTargetId(),
    library_path: $('#libraryPath').value.trim(),
    publish: $('#publishCourses').checked,
    skip_duplicates: $('#skipDuplicates').checked,
  }
}

async function beginImport() {
  if (!tokenConfigured()) { message('Hinterlege zuerst den API-Token in der lokalen Konfigurationsdatei.', true); return }
  const payload = importPayload()
  if (!payload.course_folders.length) { message('Wähle mindestens einen Kurs aus.', true); return }
  if (!payload.target_id) { message('Kein LearnHouse-Ziel konfiguriert.', true); return }
  const button = $('#importSelected'); button.disabled = true
  try {
    const data = await request('/api/import', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    state.activeJob = data.job_id
    $('#jobPanel').classList.remove('hidden')
    message('Import wurde gestartet.')
    await refreshJob(); await refreshHistory()
  } catch (error) { message(error.message, true) }
  finally { button.disabled = false }
}

function prepareImport() {
  if (!tokenConfigured()) { message('Hinterlege zuerst den API-Token in der lokalen Konfigurationsdatei.', true); return }
  const folders = selectedFolders()
  if (!folders.length) { message('Wähle mindestens einen Kurs aus.', true); return }
  if (!state.targets.length) { message('Kein LearnHouse-Ziel konfiguriert.', true); return }
  if (state.targets.length === 1) { beginImport(); return }
  $('#targetCourseCount').textContent = String(folders.length)
  const dialog = $('#targetDialog')
  if (typeof dialog.showModal === 'function') dialog.showModal()
  else beginImport()
}

function statusClass(status) { return ['success', 'partial', 'failed', 'interrupted'].includes(status) ? status : '' }

async function refreshJob() {
  if (!state.activeJob) return
  try {
    const job = await request(`/api/jobs/${encodeURIComponent(state.activeJob)}`)
    $('#jobMessage').textContent = job.message
    const badge = $('#jobStatus'); badge.textContent = job.status; badge.className = `status-badge ${statusClass(job.status)}`
    $('#progressBar').style.width = `${job.progress}%`; $('#progressValue').textContent = `${job.progress} %`
    $('#jobLog').textContent = (job.log || []).join('\n')
    if (['queued', 'running'].includes(job.status)) setTimeout(refreshJob, 1200)
  } catch (error) { message(error.message, true) }
}

async function resume(jobId) {
  try {
    const data = await request(`/api/jobs/${encodeURIComponent(jobId)}/resume`, { method: 'POST' })
    state.activeJob = data.job_id; $('#jobPanel').classList.remove('hidden'); await refreshJob(); await refreshHistory()
  } catch (error) { message(error.message, true) }
}

async function refreshHistory() {
  try {
    const data = await request('/api/jobs')
    const body = $('#historyRows'); body.replaceChildren()
    if (!data.jobs.length) {
      const row = element('tr'); const cell = element('td', 'Noch keine Importe.', 'table-empty'); cell.colSpan = 5; row.append(cell); body.append(row); return
    }
    let running = 0; let success = 0; let problems = 0
    for (const job of data.jobs) {
      if (job.status === 'running') running += 1
      if (job.status === 'success') success += 1
      if (['partial', 'failed', 'interrupted'].includes(job.status)) problems += 1
      const row = element('tr')
      row.append(element('td', job.created_at || '–'))
      const status = element('td'); status.append(element('span', job.status, `status-badge ${statusClass(job.status)}`)); row.append(status)
      row.append(element('td', `${job.progress} %`), element('td', job.message || '–'))
      const action = element('td')
      if (['partial', 'failed', 'interrupted'].includes(job.status)) {
        const button = element('button', 'Fortsetzen', 'resume-button'); button.type = 'button'; button.addEventListener('click', () => resume(job.id)); action.append(button)
      }
      row.append(action); body.append(row)
    }
    $('#runningCount').textContent = running; $('#successCount').textContent = success; $('#problemCount').textContent = problems
  } catch (error) { message(error.message, true) }
}

$('#scanButton').addEventListener('click', scan)
$('#importSelected').addEventListener('click', prepareImport)
$('#selectAll').addEventListener('change', (event) => document.querySelectorAll('.course-checkbox').forEach((box) => { box.checked = event.target.checked }))
$('#targetSelect').addEventListener('change', updateTargetDescription)
$('#confirmImport').addEventListener('click', () => { $('#targetDialog').close(); beginImport() })
$('#connectionTest').addEventListener('click', async () => {
  if (!tokenConfigured()) { message('Kein API-Token konfiguriert.', true); return }
  try {
    const result = await request('/api/connection/test', { method: 'POST', body: JSON.stringify({ target_id: selectedTargetId() }) })
    message(`Verbindung erfolgreich: ${result.organization.slug}`)
  }
  catch (error) { message(error.message, true) }
})

scan(); refreshHistory(); loadTargets()
