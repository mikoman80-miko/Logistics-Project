# Project Harness & Development Rules

## 1. 컨텍스트 및 탐색 통제 (토큰 절약)

- 전체 디렉토리 무작위 탐색(`find`, `ls -R`) 금지. 프로젝트 구조는 먼저 `docs/ARCHITECTURE.md`를 참조할 것.
- 추측성 코딩 절대 금지: 요구사항이 모호하거나 대상 파일이 불명확하면 수정 전 반드시 질문할 것.

## 2. 코딩 원칙 (Karpathy-Inspired)

- **단순함 우선:** 요청된 기능을 구현하는 가장 단순하고 직관적인 코드만 작성할 것. 요청하지 않은 추상화나 옵션 추가 금지.
- **외과적 정밀 수정:** 지정된 버그/기능과 직접 관련된 라인만 수정할 것. 기존 정상 코드의 포맷, 변수명, 스타일 임의 변경 금지.
- **프론트/백엔드 품질 기준:**
  - Frontend (Vue 3, `wms-frontend/`): Composition API(`<script setup>`) 방식 유지, ESLint 경고 0개 유지 (`wms-frontend/eslint.config.js`).
  - Backend (Python, Django는 저장소 루트): Ruff 린트 기준 준수 (`ruff.toml`). 포맷은 pre-commit이 커밋하는 파일에만 적용하므로 기존 파일을 한꺼번에 재정렬하지 말 것.

## 3. 자율 실행 및 검증 루프 (Strict Validation)

- 코드 작성/수정 후에는 반드시 터미널에서 `./verify.sh`를 실행하여 통과 여부를 확인할 것.
- **무한 루프 방지:** `./verify.sh` 실패 시 원인 분석 후 **최대 2회까지만** 자동 수정 시도할 것. 2회 내 해결되지 않으면 즉시 작업을 중단하고 실패 로그와 원인만 보고할 것.
- **간결한 보고:** 장황한 과정 설명 생략. 오직 [수정된 파일/핵심 변경점]과 [`./verify.sh` 통과 결과]만 간결하게 출력할 것.
