import 'vuetify/styles'
import { createVuetify } from 'vuetify'

export const vuetify = createVuetify({
  theme: {
    defaultTheme: 'dark',
    themes: {
      light: { colors: { primary: '#1d4ed8', secondary: '#0f766e', surface: '#ffffff', background: '#f6f7f9', warning: '#ca8a04', error: '#dc2626', success: '#15803d' } },
      dark: { colors: { primary: '#60a5fa', secondary: '#2dd4bf', surface: '#15181d', background: '#0e1013', warning: '#facc15', error: '#f87171', success: '#4ade80' } },
    },
  },
  defaults: { VBtn: { variant: 'tonal', size: 'small' }, VChip: { size: 'small' }, VTextField: { density: 'compact', variant: 'outlined' }, VSelect: { density: 'compact', variant: 'outlined' } },
})
