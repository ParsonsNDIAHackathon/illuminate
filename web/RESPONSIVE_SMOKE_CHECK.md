# Responsive viewport smoke check

Run `npm run dev` from `web/`, then inspect every route at widths **320, 375, 414, 768, 1024, and 1440 px** plus a half-width desktop window.

Routes: `/`, `/entities`, `/people`, `/artifacts`, `/claims`, `/portfolio`, `/compare/vendors`, `/connectors`, `/settings`, and an available `/entities/:id`.

At each viewport:

1. Confirm `document.documentElement.scrollWidth === document.documentElement.clientWidth`.
2. Open mobile navigation and reach every route. Confirm the theme control and graph depth control remain usable.
3. On the graph, pan/zoom, select a node and edge, use the inspector, send or type a chat prompt, toggle layers, and inspect the legend.
4. Scroll each wide data table horizontally inside its own table region; the page itself must not move sideways.
5. Open Artifact Viewer and Permission Dialog. Check tabs, long URLs, query text, actions, and close controls.
6. Check light and dark themes, browser text zoom at 200%, and touch-sized controls.

Optional console assertion:

```js
console.assert(
  document.documentElement.scrollWidth === document.documentElement.clientWidth,
  `document overflow: ${document.documentElement.scrollWidth - document.documentElement.clientWidth}px`,
)
```