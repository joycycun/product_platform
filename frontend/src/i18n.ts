import translations from './translations.en.json';

export type Language = 'zh' | 'en';
const dictionary: Record<string, string> = translations;
const originalText = new WeakMap<Text, {source: string; rendered: string}>();
const originalAttributes = new WeakMap<Element, Map<string, {source: string; rendered: string}>>();
let language: Language = localStorage.getItem('platform2-language') === 'en' ? 'en' : 'zh';
let observer: MutationObserver | undefined;
let translationProject = '';
let translationTimer: number | undefined;
let translationBusy = false;
const translatedContent = new Map<string,string>();
const pendingContent = new Set<string>();
const failedContent = new Set<string>();

export function getLanguage(): Language { return language; }

function translate(source: string): string {
  const value = source.trim();
  const exact = dictionary[value];
  if (exact) return source.replace(value, exact);
  // React renders interpolated values as separate text nodes. These prefixes
  // cover the few labels that share a text node with a dynamic value.
  for (const prefix of ['对象 ', '引用 ', '最新版本 v', '工作空间 / ', '已有账户 · ', '个项目']) {
    if (source.startsWith(prefix) && dictionary[prefix.trim()]) {
      return dictionary[prefix.trim()] + source.slice(prefix.length - (prefix.endsWith(' ') ? 1 : 0));
    }
  }
  if (language === 'en' && translationProject && /[\u3400-\u9fff]/.test(value)) {
    const parts = splitContent(value);
    const english = parts.map(part => {
      const key = translationProject + '\0' + part;
      const saved = translatedContent.get(key);
      if (!saved && !failedContent.has(key)) queueContent(key);
      return saved;
    });
    if (english.every(Boolean)) return source.replace(value, english.join(''));
  }
  return source;
}

function splitContent(value: string): string[] {
  if (value.length <= 4000) return [value];
  const parts: string[] = [];
  for (let start = 0; start < value.length;) {
    let end = Math.min(start + 3500, value.length);
    if (end < value.length) {
      const breakAt = value.lastIndexOf('\n', end);
      if (breakAt > start + 1200) end = breakAt + 1;
    }
    parts.push(value.slice(start, end));
    start = end;
  }
  return parts;
}

function queueContent(key: string): void {
  pendingContent.add(key);
  if (translationTimer !== undefined) return;
  translationTimer = window.setTimeout(() => { translationTimer = undefined; void flushContent(); }, 180);
}

async function flushContent(): Promise<void> {
  if (translationBusy || !translationProject || language !== 'en') return;
  const project = translationProject;
  const keys: string[] = [];
  let total = 0;
  for (const key of pendingContent) {
    if (!key.startsWith(project + '\0')) { pendingContent.delete(key); continue; }
    const value = key.slice(project.length + 1);
    if (keys.length >= 8 || total + value.length > 10000) break;
    keys.push(key); total += value.length; pendingContent.delete(key);
  }
  if (!keys.length) return;
  translationBusy = true;
  try {
    const response = await fetch('/api/projects/' + encodeURIComponent(project) + '/translate', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({texts: keys.map(key => key.slice(project.length + 1))})
    });
    if (!response.ok) throw new Error('Translation service unavailable');
    const result = await response.json() as {translations: Record<string,string>};
    for (const key of keys) {
      const source = key.slice(project.length + 1);
      const english = result.translations?.[source];
      if (english) translatedContent.set(key, english);
      else failedContent.add(key);
    }
    if (language === 'en' && project === translationProject) render(document.body);
  } catch {
    keys.forEach(key => failedContent.add(key));
    window.dispatchEvent(new Event('platform2-translation-error'));
  } finally {
    translationBusy = false;
    if (pendingContent.size) queueContent([...pendingContent][0]);
  }
}

function excluded(node: Node): boolean {
  const parent = node instanceof Element ? node : node.parentElement;
  if (!parent || parent.closest('code,textarea,script,style,[contenteditable="true"],[data-no-translate]')) return true;
  let closed = parent.closest('details:not([open])');
  while (closed) {
    if (closed !== parent && !closed.querySelector(':scope > summary')?.contains(parent)) return true;
    closed = closed.parentElement?.closest('details:not([open])') || null;
  }
  return false;
}

function renderText(node: Text): void {
  if (excluded(node)) return;
  const current = node.nodeValue || '';
  const prior = originalText.get(node);
  const source = prior && current === prior.rendered ? prior.source : current;
  const rendered = language === 'en' ? translate(source) : source;
  originalText.set(node, {source, rendered});
  if (rendered !== current) node.nodeValue = rendered;
}

function renderAttributes(element: Element): void {
  if (excluded(element)) return;
  const attributes = ['placeholder', 'aria-label', 'title', 'alt'];
  const originals = originalAttributes.get(element) || new Map();
  for (const name of attributes) {
    if (!element.hasAttribute(name)) continue;
    const current = element.getAttribute(name) || '';
    const prior = originals.get(name);
    const source = prior && current === prior.rendered ? prior.source : current;
    const rendered = language === 'en' ? translate(source) : source;
    originals.set(name, {source, rendered});
    if (rendered !== current) element.setAttribute(name, rendered);
  }
  originalAttributes.set(element, originals);
}

function render(root: Node): void {
  if (root.nodeType === Node.TEXT_NODE) { renderText(root as Text); return; }
  if (!(root instanceof Element) || excluded(root)) return;
  renderAttributes(root);
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (node.nodeType === Node.TEXT_NODE) renderText(node as Text);
    else renderAttributes(node as Element);
  }
}

export function setLanguage(next: Language): void {
  if (next === 'en' && language !== 'en') failedContent.clear();
  language = next;
  localStorage.setItem('platform2-language', next);
  document.documentElement.lang = next === 'zh' ? 'zh-CN' : 'en';
  document.title = next === 'zh' ? 'Zycoo · 产品设计工作台' : 'Zycoo · Product design workspace';
  render(document.body);
  window.dispatchEvent(new Event('platform2-language-change'));
}

export function setTranslationProject(pid: string): void {
  translationProject = pid;
  if (language === 'en') render(document.body);
}

export function startTranslations(): void {
  document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
  document.title = language === 'zh' ? 'Zycoo · 产品设计工作台' : 'Zycoo · Product design workspace';
  observer = new MutationObserver(records => {
    for (const record of records) {
      if (record.type === 'childList') {
        record.addedNodes.forEach(render);
      } else if (record.type === 'characterData') {
        renderText(record.target as Text);
      } else if (record.type === 'attributes') {
        if (record.attributeName === 'open') render(record.target);
        else renderAttributes(record.target as Element);
      }
    }
  });
  observer.observe(document.body, {subtree: true, childList: true, characterData: true, attributes: true,
    attributeFilter: ['placeholder', 'aria-label', 'title', 'alt', 'open']});
  render(document.body);
}
