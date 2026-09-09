import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'graph', component: () => import('./views/Explorer.vue') },
    { path: '/entities', name: 'entities', component: () => import('./views/Entities.vue') },
    // An entity link opens the entity on the canvas. The long form is no longer a page that
    // exists while you look at it — it is a Report node the user generates and keeps.
    { path: '/entities/:id', name: 'entity', component: () => import('./views/EntityOpen.vue'), props: true },
    { path: '/people', name: 'people', component: () => import('./views/People.vue') },
    { path: '/risk', name: 'risk', component: () => import('./views/Risk.vue') },
    { path: '/reports', name: 'reports', component: () => import('./views/Reports.vue') },
    { path: '/reports/:id', name: 'report', component: () => import('./views/Reports.vue'), props: true },
    { path: '/artifacts', name: 'artifacts', component: () => import('./views/Artifacts.vue') },
    { path: '/claims', name: 'claims', component: () => import('./views/Claims.vue') },
    { path: '/connectors', name: 'connectors', component: () => import('./views/Connectors.vue') },
    { path: '/settings', name: 'settings', component: () => import('./views/Settings.vue') },
  ],
})
