/* #240 UX-2a. Presentation-only project resume links; Core owns every business action. */
const MAX_VISIBLE_PROJECTS = 4;

export function selectResumeProjects(raw, limit = MAX_VISIBLE_PROJECTS) {
  if (!Array.isArray(raw) || !Number.isInteger(limit) || limit < 1) return [];
  const result = [];
  const seen = new Set();
  for (const project of raw) {
    if (!project || typeof project.project_id !== 'string' ||
        typeof project.title !== 'string' || !project.title.trim() ||
        project.status === 'archived' || seen.has(project.project_id)) continue;
    seen.add(project.project_id);
    result.push({ id: project.project_id, title: project.title.trim() });
    if (result.length >= Math.min(limit, MAX_VISIBLE_PROJECTS)) break;
  }
  return result;
}

export function renderResumeProjects(host, projects, onOpenProject, isCurrent, onError) {
  if (!isCurrent()) return;
  const entries = selectResumeProjects(projects);
  if (!entries.length) {
    host.replaceChildren();
    return;
  }
  const section = document.createElement('section');
  section.className = 'resume-projects';
  section.setAttribute('aria-label', '招聘项目快捷入口');

  const heading = document.createElement('div');
  heading.className = 'resume-heading';
  const title = document.createElement('h2');
  title.textContent = '招聘项目快捷入口';
  const note = document.createElement('p');
  note.textContent = '按项目列表显示前四项；不是待办优先级，具体下一步由项目工作区实时确定。';
  heading.append(title, note);
  section.appendChild(heading);

  const list = document.createElement('div');
  list.className = 'resume-list';
  for (const entry of entries) {
    const row = document.createElement('div');
    row.className = 'resume-entry';
    const name = document.createElement('span');
    name.className = 'resume-project-title';
    name.textContent = entry.title;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn small';
    button.textContent = '进入工作区';
    button.setAttribute('aria-label', '进入工作区 · ' + entry.title);
    button.addEventListener('click', () => {
      if (!isCurrent() || button.disabled) return;
      button.disabled = true;
      try {
        Promise.resolve(onOpenProject(entry.id))
          .catch(error => { if (isCurrent()) onError(error); })
          .finally(() => { button.disabled = false; });
      } catch (error) {
        button.disabled = false;
        if (isCurrent()) onError(error);
      }
    });
    row.append(name, button);
    list.appendChild(row);
  }
  section.appendChild(list);
  host.replaceChildren(section);
}

export async function mountProjectResume(host, loadProjects, onOpenProject, isCurrent, onError) {
  try {
    const result = await loadProjects();
    if (!isCurrent()) return;
    renderResumeProjects(host, result?.projects, onOpenProject, isCurrent, onError);
  } catch (error) {
    // A secondary navigation shortcut must never break a primary Core queue.
    if (isCurrent()) host.replaceChildren();
  }
}
