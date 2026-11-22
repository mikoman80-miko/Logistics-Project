// 화면 코드 린트: ESLint 기본 권장 규칙 + Vue 3 필수 규칙(오류 방지, 서식 규칙 제외). 경고 0개를 유지합니다. (npx eslint src --max-warnings=0)
import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import globals from 'globals'

export default [
  { ignores: ['dist/**', 'e2e/results/**', 'e2e/screens/**'] },
  js.configs.recommended,
  ...pluginVue.configs['flat/essential'],
  {
    languageOptions: { globals: { ...globals.browser } },
    rules: {
      // Barcode, Pager처럼 한 단어 이름의 공통 컴포넌트를 씁니다.
      'vue/multi-word-component-names': 'off',
      // 폼 객체를 넘겨 그 안의 칸을 고치는 방식(model.q = …)은 허용하고, prop 자체를 바꾸는 것만 막습니다.
      'vue/no-mutating-props': ['error', { shallowOnly: true }],
      // 일부 칸을 빼고 나머지를 보내는 구조 분해({ id, ...change })는 허용합니다.
      'no-unused-vars': ['error', { ignoreRestSiblings: true }],
    },
  },
  {
    files: ['e2e/**', '*.config.js'],
    languageOptions: { globals: { ...globals.node } },
  },
]
