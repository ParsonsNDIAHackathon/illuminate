import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'graph', component: () => import('./views/Explorer.vue') },
    { path: '/data/:section?', name: 'data', component: () => import('./views/Data.vue'), props: true },
    { path: '/entities', redirect: '/data/entities' },
    // A link to a party opens its page: the whole record on one screen, with a button to put
    // it on the canvas. The canvas card is the glance; these are the detail.
    { path: '/entities/:id', name: 'entity', component: () => import('./views/EntityReport.vue'), props: true },
    { path: '/people', redirect: '/data/people' },
    { path: '/people/:id', name: 'person', component: () => import('./views/PersonReport.vue'), props: true },
    { path: '/risk', redirect: '/data/risk' },
    { path: '/reports', name: 'reports', component: () => import('./views/Reports.vue') },
    { path: '/reports/:id', name: 'report', component: () => import('./views/Reports.vue'), props: true },
    { path: '/artifacts', redirect: '/data/artifacts' },
    { path: '/claims', redirect: '/data/claims' },
    { path: '/connectors', redirect: '/settings/connectors' },
    { path: '/settings/:section?', name: 'settings', component: () => import('./views/Settings.vue'), props: true },
  ],
})
