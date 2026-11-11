# 검증 결과 — 2026-11-11

## 로컬 자동 검증

명령: `.venv/bin/python -m pytest -q` → **40 passed** (Python 3.14.5, macOS).

실패: 0. 외부 라이브러리 경고 1: Starlette 1.x 테스트 클라이언트가 httpx 사용 중단 예고를 표시합니다. 실제 테스트 실행·서버 요청은 정상이며, 테스트 HTTP 클라이언트 교체는 별도 의존성 업데이트 시 검토합니다.

| 요구 테스트 | 결과 / 근거 |
|---|---|
| 정상 주문 생성/이름/금액 일치 | 성공, tests/test_store.py |
| 입금 데이터 수신/미검증 기본값 | 성공, 알림 수신만으로 메일 작업 없음 |
| 이름·금액 불일치 | 성공, PENDING 유지 |
| 동일 이름 중복 주문 | 성공, REVIEW_REQUIRED. 나중 중복 주문도 기존 매칭 무효화 |
| 동일 입금 재전송 | 성공, 동시 4건 중 하나만 생성, 나머지 동일 이벤트 반환 |
| 주문 만료/허용 시간창 | 성공, 만료 주문과 과거/미래 시각 처리 |
| 메일 실패/재시도/재발송 | 성공, 같은 본문·키, 영구 오류·멱등창 종료, 재발급 시 구 링크 폐기 |
| 다운로드 만료/인증/환불 | 성공, 해시 저장·기한·폐기·파일 비공개 검증 |
| 잘못된 API 키/관리자 인증 | 성공, 권한 분리·401 |
| 서버 재생성 후 데이터 유지 | 성공, 같은 DB로 새 앱을 생성해 조회/매칭 |
| 악성 입력/과다 요청 | 성공, SQL/XSS/CSV 수식·크기·CORS·rate limit |
| 동시 입금/승인/발송 | 성공, 자동 승인 없음, 활성 작업·메일 한 건 |
| 전송 직후 프로세스 종료 모사 | 성공, BaseException으로 네트워크 직후 종료를 모사하고 동일 본문/키로 재개 |
| SQLite 백업/launchd 생성 | 성공, backup integrity_check, plist 설정 검증 |
| Pages 산출물 격리 | 성공, 4개 파일만 포함, 개인정보 폼·API 호출 없음 |
| 실판매 오설정 차단 | 성공, 모의 계좌·MOCK ZIP·불일치 파일 해시·미검토 정책 차단 |

추가: `compileall` 성공, shell `sh -n` 성공, `plutil -lint` server/backup 모두 OK.

## 브라우저 검증

격리된 모의 서버(127.0.0.1:8001, 별도 테스트 DB/키/우편함)에서 실제 UI 동작:

1. 구매 폼 입력·동의·주문 저장·비밀 조회 토큰 표시.
2. 관리자 로그인·수동 모의 입금 저장 → MATCHED_UNVERIFIED.
3. 확인 기록·모의 은행 확인 체크 후 승인 → PAID_VERIFIED.
4. 메일 큐 처리 → SENT, 모의 우편함 표시.
5. 브라우저에서 ZIP 실제 다운로드 완료. ZIP은 MOCK-ONLY 안내 파일.
6. 데모 네 단계 PENDING → MATCHED_UNVERIFIED → PAID_VERIFIED → SENT 전환.
7. 데스크톱과 390px 모바일 화면 확인. 모바일 가로 넘침 없음.

## 독립 리뷰

독립 코드 검토에서 2개 중요 문제 재현: 모의 상품을 실판매 설정으로 허용, 부분 저장된 모의 메일 파일을 성공으로 오판. 각각 실패 테스트 작성 후 실제 상품 해시/MOCK 차단, atomic mail write/부분파일 복구로 수정. 추가로 복수 알림·잘못된 금액 쉼표를 추측하지 않도록 실패 테스트 후 파서를 수정했습니다. 최종 전체 40개 통과. 검증된 은행 데이터 공급자는 연결되지 않았습니다.

## 외부 환경 — 구분 필요

- GitHub Pages 배포: **성공**, https://ginoufjq.github.io/analog-keyboard-store/ 에서 실제 화면과 체험 버튼 동작 확인. 첫 실행은 Pages 활성화 전에 시작되어 configure-pages 404로 실패했고, 설정 완료 후 동일 워크플로 재실행 성공. [배포 실행 기록](https://github.com/ginoufJQ/analog-keyboard-store/actions/runs/42962647265)
- GitHub 원격 CI: Linux Python 3.11 / 3.14 환경 모두 성공. [테스트 실행 목록](https://github.com/ginoufJQ/analog-keyboard-store/actions/workflows/test.yml)
- GitHub Pages에서 실제 주문 API 호출: **수행하지 않음**. Pages 상거래 제한 때문에 의도적으로 분리했으며, 실제 주문은 맥북 사이트에서 제공합니다.
- iPhone 실기기 HTTPS POST / 오프라인 복구: **미검증**, 실제 도메인/터널/기기 설정 필요.
- Cloudflare DNS/Tunnel/Access/WAF: **미설정·미검증**, 사용자 계정과 도메인 필요.
- Resend 실제 발송/수신/반송: **미검증**, 제공자 HTTP 계약은 모의 응답으로 검증.
- 토스 실제 계좌/실입금/푸시 원문 자동 수집: **미검증·미활성화**.
- macOS launchd 설치·실제 재부팅·절전 복구: **미실행**, 파일 생성·형식만 검증.
- 실제 EXE 실행·지원 키보드·제품 품질: **미검증**, 실제 제품 파일 필요.

운영 환경 검증을 대신해 성공으로 표시하지 않습니다. `docs/go-live.md` 체크리스트가 남은 설정 작업입니다.
