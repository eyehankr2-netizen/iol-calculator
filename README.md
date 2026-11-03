# IOL Calculator

해외 백내장 봉사 현장에서 인터넷 없이 갤럭시 폰으로 쓰는 IOL 도수 계산기입니다. SRK/T, Hoffer Q, Holladay 1, SRK II 네 공식을 고를 수 있습니다.

## 앱 주소

```
https://eyehankr2-netizen.github.io/iol-calculator/
```

폰에서 이 주소를 열고 홈 화면에 추가하면, 그 뒤로는 인터넷 없이 동작합니다. 자세한 방법은 `docs/설치_및_사용법.md`에 있습니다. 소스는 https://github.com/eyehankr2-netizen/iol-calculator 에 있습니다.

## 폴더 구성

| 위치 | 내용 |
|---|---|
| `app/` | 폰에 넣는 앱. `index.html` 하나만으로 동작합니다. 나머지 파일은 홈 화면 설치와 오프라인 동작용입니다. |
| `docs/설치_및_사용법.md` | PC와 폰에서 여는 법, 현장 사용 순서 |
| `docs/검증결과.md` | 엑셀 수식, 독립 구현과의 비교 결과와 엑셀에서 발견한 문제 |
| `docs/screenshots/` | 폰 화면 사진 |
| `tests/` | 검증 스크립트 (개발용) |
| `Copy of doubleK_계산용_전공의.xlsx` | 원본 엑셀. 수정하지 않았습니다. |

## 개발 메모

- 계산 엔진은 `app/index.html` 안의 `IOL ENGINE START`와 `IOL ENGINE END` 사이에 있습니다.
- 앱을 고치면 `index.html`의 `VERSION`과 `sw.js`의 `CACHE`를 함께 올립니다.
- 엔진을 고치면 `tests/reference_impl.py`를 실행해 자가진단 기준값을 다시 넣고, `tests/run_engine_tests.py`와 `tests/run_ui_tests.py`가 모두 통과하는지 확인합니다.
- 렌즈 데이터에는 나중의 재고 관리 기능을 위한 `stock` 칸이 비어 있는 상태로 들어 있습니다.
