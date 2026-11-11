# 운영 매뉴얼

## 안전한 기본 동작

`PENDING → MATCHED_UNVERIFIED → PAID_VERIFIED → SENT`.

알림 텍스트는 미검증입니다. `source`는 신뢰 등급이 아니며 모든 공개 입금 요청은 미검증으로 저장합니다. 관리자 승인은 실제 은행 내역과 대조한 입금 ID, `bank_checked=true`, 확인 사유가 필요합니다. 은행 API 자동 승인은 구현 경계만 있으며 활성화되지 않았습니다.

매칭: 이름 NFKC/공백 제거/casefold + 주문 당시 금액 + 입금 시각 `[주문 생성 - 15분, 주문 만료]` + 정확히 한 주문/한 입금. 입금이 먼저 도착해도 15분 이내 나중 주문과 매칭합니다. 후보가 여러 개면 `REVIEW_REQUIRED`. 과거/늦은 입금은 저장되지만 자동 매칭되지 않습니다. 서버/아이폰의 날짜·시간 자동 설정을 켜세요.

같은 이름·금액·UTC 초 단위 시각·source는 동일 이벤트로 취급합니다. 같은 초의 실제 별도 입금은 구별되지 않으므로 은행 내역으로 확인해야 합니다. 시각/source가 바뀐 재입력은 별도 이벤트입니다. 검증된 은행 거래 고유 ID가 없는 한 완전한 금융 중복 방지는 불가능합니다.

## 매일 확인

```sh
.venv/bin/python scripts/healthcheck.py
.venv/bin/python scripts/backup.py
```

관리자에서 검증 대기, 중복 검토, 메일 실패, 만료 후 입금, 지원 문의를 확인합니다. UI는 주문·입금 페이지 이동을 지원합니다. 이메일 작업은 최신 100건, 모의 우편함은 20건을 표시하며 API offset으로 더 조회할 수 있습니다. CSV는 전체 주문입니다. CSV 파일에도 개인정보가 포함되므로 공개 저장소에 두지 마세요.

## 메일·재시도

- 모의 모드: `var/mock-mail/<job-id>.json`에 실제 본문을 저장. 이는 로컬 수신함이며 다운로드 토큰 원문이 들어 있으므로 600/700 권한으로 보호합니다. DB에는 토큰 해시만 저장하고, 전송 재시도용 본문은 Fernet 암호화합니다.
- Resend 모드: `POST /emails`, `Idempotency-Key: download/<job-id>`. 공급자 멱등키 유효기간은 24시간입니다. 동일 작업은 고정 암호화 본문·동일 링크를 사용하며 외부 전송 **전에** DB에 커밋됩니다. [Resend 멱등키](https://resend.com/docs/dashboard/emails/idempotency-keys)
- 60/120/240/480초 간격 등 지수 대기, 최대 5회. 네트워크·429·5xx만 재시도하고 영구 오류는 실패 처리합니다. 최초 시도로부터 23시간이 지나면 자동 재시도하지 않습니다.
- worker는 5초 간격, 건당 15초의 공급자 요청 상한. SQLite 쓰기 트랜잭션으로 메일 발송과 승인/취소/재발급을 직렬화합니다. 소규모 판매용이며 대량 발송에서는 외부 작업 큐로 분리해야 합니다.
- `SENT`는 공급자가 요청을 수락했다는 뜻입니다. 수신함 도착/읽음 보장이 아니며 반송 추적 웹훅은 연결하지 않았습니다.
- 실패 후 진행 중 작업은 자동 재시도를 기다립니다. 종료된 작업은 관리자 `메일·링크 재발급`으로 **기존 링크 폐기 + 새 메일 작업**을 만듭니다. 공급자에서 이미 보냈을 가능성이 있는 네트워크 장애는 Resend 기록을 먼저 확인하세요. 관리자가 의도적으로 재발급한 메일은 새 메일입니다.

## 다운로드 / 취소 / 환불

공개 GitHub Release는 사용하지 않습니다. `private/`의 단일 설정 파일을 토큰 검증 후 전송합니다. 토큰은 32바이트 이상 임의값, DB에는 SHA-256, 최초 발송 시도부터 24시간, 다운로드 횟수 기록. 환불·재발급 시 토큰 폐기. 한 번 이미 내려받은 파일을 원격 삭제할 수는 없습니다.

입금 전 취소는 `CANCELLED`; 승인 후에는 실제 환불 완료 확인 후 `REFUNDED`로 기록합니다. **버튼은 은행 송금이나 환불을 실행하지 않습니다.** 작업 중 발송과 경쟁하지 않도록 DB에서 직렬화합니다. 주문번호·입금 ID·사유·작업 시각은 감사 로그에 기록하며 `/api/admin/audit`로 조회합니다.

## macOS launchd (생성만 수행, 설치는 운영자 선택)

```sh
.venv/bin/python scripts/generate_launchd.py
mkdir -p "$HOME/Library/LaunchAgents"
cp deploy/generated/com.analog.store.plist "$HOME/Library/LaunchAgents/"
cp deploy/generated/com.analog.store.backup.plist "$HOME/Library/LaunchAgents/"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.analog.store.plist"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.analog.store.backup.plist"
```

수동 서버를 먼저 종료해 8000 포트 충돌을 피하세요. 현재 체크아웃 절대경로와 가상환경이 plist에 포함됩니다. 프로젝트 이동 시 다시 생성합니다. KeepAlive로 비정상 종료 후 재시작, 매일 로컬 시간 04:15 온라인 SQLite 백업. LaunchAgent는 **사용자 로그인 후** 실행됩니다. 전원 켜짐/로그인 전 실행이 필요하면 별도 LaunchDaemon과 FileVault 운영 정책 검토가 필요합니다.

```sh
launchctl print "gui/$(id -u)/com.analog.store"
launchctl kickstart -k "gui/$(id -u)/com.analog.store"
launchctl bootout "gui/$(id -u)/com.analog.store"
```

## 로그와 저장 공간

`var/log/server.log`는 2MB × 최대 6개 파일로 회전합니다. access log를 끄므로 다운로드 URL 원문을 남기지 않습니다. `com.analog.*.out.log/err.log`는 launchd 초기화 실패용 보조 로그로, 문제 해결 후 비정상 반복 재시작을 먼저 중단하고 파일 크기를 확인하세요. 백업/모의 우편함은 자동 파기하지 않으므로 운영자가 보유 정책에 맞춰 정리해야 합니다.

## 백업·복원

`scripts/backup.py`는 SQLite online backup API를 사용하고 integrity_check 후 600 권한으로 저장합니다. WAL 파일을 생략한 단순 DB 복사를 하지 않습니다. 같은 디스크의 백업만으로는 맥북 분실/고장을 대비할 수 없습니다. 암호화된 별도 저장장치에 DB와 **.env의 OUTBOX_ENCRYPTION_KEY**를 함께 안전하게 보관하세요. 키가 없으면 대기 메일 본문을 복호화할 수 없습니다. API 키는 별도 비밀 저장소에서 관리하고 유출 시 회전합니다.

복원 연습:

1. 서버·worker 종료. 원본 DB와 `-wal`, `-shm`은 별도 복구 폴더에 함께 보존합니다.
2. 검증된 백업을 **새 경로**로 복사하고 `.env`의 `DATABASE_PATH`를 새 파일로 지정합니다. 실행 중 DB 위에 덮어쓰지 않습니다.
3. 같은 암호화 키로 실행하되 `WORKER_ENABLED=false`로 시작. 주문 건수와 메일 작업 상태 확인.
4. 백업 시점 이후 이미 전송된 메일이 있을 수 있으므로 공급자 기록과 비교합니다. 23시간 경과 작업은 자동 재시도하지 않습니다. 오래된 백업으로 결제/발송을 무조건 재실행하지 않습니다.
5. 확인 후 worker 재활성화. 모의 주문·조회·다운로드 테스트.

## 상시 운영 점검

전원 연결, macOS의 전원 어댑터 연결 시 자동 잠자기 방지 설정, 안정적인 네트워크, 정확한 시각을 확인합니다. 필요 시 테스트 동안 `caffeinate -is`를 사용합니다. 덮개 닫힘·macOS 업데이트·FileVault·로그인 전 상태는 별도 검증하세요. 재부팅 테스트는 작업을 저장한 뒤 운영자가 직접 실행합니다. 이 작업에서는 재부팅·절전 설정 변경을 수행하지 않았습니다.

## 장애 대응 예

| 증상 | 점검 / 조치 |
|---|---|
| 서버 시작 실패 | .env 키·권한, 가상환경, 포트 중복, server.log 확인 |
| 401 | 관리자 Bearer 키와 입금 X-API-Key 혼동 확인 |
| 422 | 정수 금액, 시간대 포함 ISO 시각, 필수 동의·은행 확인 항목 확인 |
| 매칭 안 됨 | 저장된 주문 금액·정규화 이름·15분 시간창·만료·중복 후보 확인 |
| EMAIL_FAILED | 관리자 email-jobs의 오류 코드, Resend 도메인 인증/발신자/할당량 확인 |
| 링크 404 | 만료·환불·재발급·잘못된 토큰 확인. 개인정보 확인 후 관리자 재발급 |
| 링크 503 | PRODUCT_FILE 경로와 실제 ZIP/EXE 읽기 권한 확인 |
| 429 | Retry-After 대기, Cloudflare IP 전달·남용 여부 확인 |
| 외부만 연결 실패 | Tunnel 상태·DNS·Access 정책·맥북 절전/네트워크 확인 |
