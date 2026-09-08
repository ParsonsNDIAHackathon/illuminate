import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'graph', component: () => import('./views/Explorer.vue') },
    { path: '/entities', name: 'entities', component: () => import('./views/Entities.vue') },
    { path: '/entities/:id', name: 'report', component: () => import('./views/EntityReport.vue'), props: true },
    { path: '/compare/vendors', name: 'vendor-comparison', component: () => import('./views/VendorComparison.vue') },
    { path: '/people', name: 'people', component: () => import('./views/People.vue') },
    { path: '/artifacts', name: 'artifacts', component: () => import('./views/Artifacts.vue') },
    { path: '/claims', name: 'claims', component: () => import('./views/Claims.vue') },
    { path: '/connectors', name: 'connectors', component: () => import('./views/Connectors.vue') },
    { path: '/settings', name: 'settings', component: () => import('./views/Settings.vue') },
  ],
})
