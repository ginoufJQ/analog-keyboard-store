# Analog Keyboard Controller — 주문·입금 확인·비공개 배포

FastAPI + SQLite로 동작하는 개인 개발자용 시스템입니다. **기본은 모의 운영이며 실제 돈이나 메일을 보내지 않습니다.** 입금 정보는 자동 매칭되지만, 은행 거래내역을 확인한 관리자의 승인 후에만 발송합니다.

## 빠른 실행 (macOS / Python 3.11+)

```sh
sh scripts/setup.sh
sh scripts/run.sh
```

- 구매 페이지: <http://127.0.0.1:8000/>
- 관리자: <http://127.0.0.1:8000/admin> — `.env`의 `ADMIN_API_KEY` 입력
- GitHub Pages 체험 화면 로컬 미리보기: <http://127.0.0.1:8000/demo/>
- 상태 점검: `.venv/bin/python scripts/healthcheck.py`
- 전체 자동 테스트: `.venv/bin/python -m pytest -q`

`.env`는 setup이 안전한 임의 키로 생성합니다. 키는 터미널에 출력하지 않습니다. 처음 생성되는 ZIP은 **MOCK-ONLY 텍스트만 들어 있는 모의 파일**입니다. 실제 Windows 프로그램을 제공한 것이 아닙니다. 제품의 실제 기능·스크린샷·호환 키보드·버전은 개발자가 제공해야 합니다.

## 모의 주문 1건 끝까지 처리

1. 구매 페이지에 `buyer@example.com`, `모의구매자` 입력 후 동의하고 주문 생성.
2. 주문번호와 비밀 조회 토큰을 로컬 파일로 저장. 토큰은 재표시·복구할 수 없습니다.
3. 관리자 로그인 → 수동 입금 입력: 같은 이름, 3,000원, 현재 시각.
4. 주문이 `MATCHED_UNVERIFIED`인지 확인. 이 단계에서는 메일이 나가지 않습니다.
5. 주문의 `승인 선택`, 입금의 `입금 선택` → 확인 기록에 `모의 승인 테스트` → 확인 체크 후 승인.
6. 5초 내 worker가 처리하거나 `메일 큐 처리` 클릭.
7. 관리자 아래 모의 우편함을 열어 다운로드. ZIP 안에는 모의 안내문만 있습니다.
8. 재발급하면 기존 링크는 폐기되고 새 링크가 생성됩니다. 만료는 최초 발송 시도부터 24시간입니다.

## 폴더

```text
backend/              FastAPI, 설정, SQLite 스키마, 매칭, 메일, 검증 어댑터 경계
backend/templates/    다운로드 안내 메일 본문
web/                  실제 구매 페이지와 별도 관리자 대시보드
pages/                개인정보 없는 비상업적 GitHub Pages 데모
scripts/              설치, 실행, Pages 빌드, 백업, launchd 생성, 점검
deploy/               Cloudflare 설정 예제와 생성된 launchd 파일
tests/                API/매칭/보안/메일/다운로드/영속성 테스트
docs/                 운영·아이폰·Cloudflare·법적 검토·검증 기록
.github/workflows/    테스트 CI 및 Pages 데모 배포
private/              비공개 EXE/ZIP (Git 제외)
var/                  DB, 로그, 백업, 모의 우편함 (Git 제외)
```

## GitHub Pages와 실제 구매 사이트

GitHub 공식 규정은 Pages를 상거래 중심 사이트의 무료 호스팅으로 사용하는 것을 허용하지 않습니다. 이 프로젝트의 Pages 빌드는 **체험 화면 4개 파일만** 게시하며 구매 폼·계좌·주문 API 호출을 포함하지 않습니다. 실제 구매 페이지는 Cloudflare Tunnel을 통해 맥북에서 제공합니다. [GitHub Pages 제한](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)

새 GitHub 저장소의 Settings → Pages → Source를 GitHub Actions로 설정하고 `Publish noncommercial demo` 워크플로를 실행합니다. 공개 전 빌드 산출물 `dist/`를 확인하세요. GitHub 저장소에는 비밀·실거래 데이터·제품 파일을 올리지 않습니다.

## 운영 전 읽기

- [운영 매뉴얼](docs/operations.md): 상태, 장애 복구, 백업, 보안, macOS 자동 실행
- [아이폰 단축어 가이드](docs/iphone-shortcut.md): 수동 입력·정규식·JSON·재전송
- [Cloudflare Tunnel](docs/cloudflare.md): 도메인, HTTPS, Access, WAF
- [출시·법적 검토](docs/go-live.md): 실제 계정·정책·제품 준비
- [API 예시](docs/api.md)
- [검증 결과](docs/verification.md)

공식 은행 API는 연결되어 있지 않습니다. `backend/verification.py`는 향후 실제 제공자 연동을 위한 추상 인터페이스입니다. `source`나 `verified=true`로 자동 승인할 수 없습니다. iPhone 실제 기기·외부 HTTPS·Resend 실발송·재부팅 복구는 별도 실제 환경 검증이 필요합니다.
