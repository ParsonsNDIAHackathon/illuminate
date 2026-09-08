import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'mission', component: () => import('./views/MissionEntry.vue') },
    { path: '/explorer', name: 'graph', component: () => import('./views/Explorer.vue') },
    { path: '/entities', name: 'entities', component: () => import('./views/Entities.vue') },
    { path: '/programs', name: 'programs', component: () => import('./views/Programs.vue') },
    { path: '/portfolio', name: 'portfolio', component: () => import('./views/Portfolio.vue') },
    { path: '/entities/:id', name: 'report', component: () => import('./views/EntityReport.vue'), props: true },
    { path: '/compare/vendors', name: 'vendor-comparison', component: () => import('./views/VendorComparison.vue') },
    { path: '/people', name: 'people', component: () => import('./views/People.vue') },
    { path: '/artifacts', name: 'artifacts', component: () => import('./views/Artifacts.vue') },
    { path: '/claims', name: 'claims', component: () => import('./views/Claims.vue') },
    { path: '/interoperability', name: 'interoperability', component: () => import('./views/FindingsInteroperability.vue') },
    { path: '/connectors', name: 'connectors', component: () => import('./views/Connectors.vue') },
    { path: '/settings', name: 'settings', component: () => import('./views/Settings.vue') },
  ],
})

const focusByLocation = new Map<string, string>()
let focusObserver: MutationObserver | null = null
let focusFallbackTimer: number | null = null
let focusExpiryTimer: number | null = null

function focusSelector(element: HTMLElement) {
  if (element.id) return `#${CSS.escape(element.id)}`
  if (element.dataset.routeFocusKey) return `[data-route-focus-key="${CSS.escape(element.dataset.routeFocusKey)}"]`
  const href = element.getAttribute('href')
  if (href) return `${element.tagName.toLowerCase()}[href="${CSS.escape(href)}"]`
  const label = element.getAttribute('aria-label')
  if (label) return `${element.tagName.toLowerCase()}[aria-label="${CSS.escape(label)}"]`
  return ''
}

router.beforeEach((_, from) => {
  const active = document.activeElement
  if (active instanceof HTMLElement && active !== document.body) {
    const selector = focusSelector(active)
    if (selector) focusByLocation.set(from.fullPath, selector)
  }
})

router.afterEach(async to => {
  focusObserver?.disconnect()
  if (focusFallbackTimer != null) window.clearTimeout(focusFallbackTimer)
  if (focusExpiryTimer != null) window.clearTimeout(focusExpiryTimer)
  await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
  const savedSelector = focusByLocation.get(to.fullPath)
  const headingSelector = 'main h1, main h2, [data-route-heading], h1, h2'
  let allowHeadingFallback = !savedSelector
  const focusElement = (selector: string) => {
    const target = document.querySelector<HTMLElement>(selector)
    if (!target) return false
    if (!target.matches('a, button, input, select, textarea, [tabindex]')) target.tabIndex = -1
    target.focus({ preventScroll: true })
    return document.activeElement === target
  }
  const focus = () => {
    if (savedSelector && focusElement(savedSelector)) return true
    return allowHeadingFallback && focusElement(headingSelector)
  }
  if (focus()) return
  focusObserver = new MutationObserver(() => {
    if (focus()) {
      focusObserver?.disconnect()
      focusObserver = null
    }
  })
  focusObserver.observe(document.querySelector('#app') || document.body, { childList: true, subtree: true })
  focusFallbackTimer = window.setTimeout(() => {
    allowHeadingFallback = true
    if (focus()) focusObserver?.disconnect()
  }, 750)
  const observer = focusObserver
  focusExpiryTimer = window.setTimeout(() => {
    observer.disconnect()
    if (focusObserver === observer) focusObserver = null
  }, 10000)
})
