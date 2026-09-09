import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', alias: '/explorer', name: 'graph', component: () => import('./views/Explorer.vue') },
    { path: '/entities', name: 'entities', component: () => import('./views/Entities.vue') },
    // A link to a party opens its page: the whole record on one screen, with a button to put
    // it on the canvas. The canvas card is the glance; these are the detail.
    { path: '/entities/:id', name: 'entity', component: () => import('./views/EntityReport.vue'), props: true },
    { path: '/people', name: 'people', component: () => import('./views/People.vue') },
    { path: '/people/:id', name: 'person', component: () => import('./views/PersonReport.vue'), props: true },
    { path: '/risk', name: 'risk', component: () => import('./views/Risk.vue') },
    { path: '/reports', name: 'reports', component: () => import('./views/Reports.vue') },
    { path: '/reports/:id', name: 'report', component: () => import('./views/Reports.vue'), props: true },
    { path: '/artifacts', name: 'artifacts', component: () => import('./views/Artifacts.vue') },
    { path: '/claims', name: 'claims', component: () => import('./views/Claims.vue') },
    { path: '/connectors', name: 'connectors', component: () => import('./views/Connectors.vue') },
    { path: '/settings', name: 'settings', component: () => import('./views/Settings.vue') },
  ],
})
