import { ref } from 'vue'

/**
 * A source link opens the page in a modal frame by default; the usual modifier
 * clicks (ctrl/cmd/shift/alt, middle button) fall through to the browser so the
 * link still opens in a new tab.
 */
export function useSourceFrame() {
  const frameUrl = ref<string | null>(null)

  function openFrame(e: MouseEvent, url?: string | null) {
    if (!url) return
    if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return
    e.preventDefault()
    frameUrl.value = url
  }

  return { frameUrl, openFrame }
}

export function hostOf(url?: string | null) {
  try { return new URL(url || '').hostname.replace(/^www\./, '') } catch { return '' }
}
