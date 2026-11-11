# API 사용 예

모든 예시는 모의 운영 기준입니다. 인증키·실계좌·개인정보를 커맨드 인자나 공개 이슈에 복사하지 마세요. Python 예시는 `.env`를 읽고 헤더에만 키를 넣습니다. 키를 URL 쿼리로 전달하지 않습니다.

## 실제 모의 주문 → 미검증 입금 → 승인 → 메일

아래를 프로젝트 루트에서 `.venv/bin/python`으로 실행합니다. 현재 로컬 서버가 실행 중이어야 합니다.

```python
from datetime import datetime, timezone
import httpx
from dotenv import dotenv_values

env = dotenv_values('.env')
base = 'http://127.0.0.1:8000'
admin = {'Authorization': 'Bearer ' + env['ADMIN_API_KEY']}
deposit_auth = {'X-API-Key': env['DEPOSIT_API_KEY']}
with httpx.Client(base_url=base, timeout=30) as c:
    r = c.post('/api/orders', json={
        'email': 'mock@example.com', 'depositor_name': '모의구매자',
        'privacy_consent': True,
    })
    r.raise_for_status()
    order = r.json()  # status_token 원문은 이 응답에서 한 번만 받습니다.
    lookup = {'Authorization': 'Bearer ' + order['status_token']}
    payload = {
        'depositor_name': '모의구매자', 'amount': order['amount'],
        'received_at': datetime.now(timezone.utc).isoformat(),
        'source': 'mock', 'raw_notification': '실제 입금 아님',
    }
    r = c.post('/api/deposits', headers=deposit_auth, json=payload)
    r.raise_for_status()
    deposit = r.json()
    assert c.post('/api/deposits', headers=deposit_auth, json=payload).status_code == 200
    assert c.get(f"/api/orders/{order['id']}/status", headers=lookup).json()['status'] in ('MATCHED_UNVERIFIED','REVIEW_REQUIRED')
    r = c.post(f"/api/admin/orders/{order['id']}/approve", headers=admin, json={
        'deposit_id': deposit['id'], 'bank_checked': True,
        'note': '모의 데이터 수동 승인 테스트 — 실제 입금 아님',
    })
    r.raise_for_status()
    c.post('/api/admin/email-jobs/process', headers=admin).raise_for_status()
    print(c.get(f"/api/orders/{order['id']}/status", headers=lookup).json()['status'])
```

## 엔드포인트

| 메서드 / 경로 | 인증 | 용도 |
|---|---|---|
| GET /health | 없음 | DB 생존 확인, mock/live |
| GET /api/config | 없음 | 가격·지원정보·버전 (계좌·키·주문 없음) |
| POST /api/orders | 없음 | 서버 가격으로 주문, 동의 필수 |
| GET /api/orders/{id}/status | 주문 Bearer 토큰 | 상태만 조회, 타인 이메일·이름 미노출 |
| POST /api/deposits | X-API-Key | 미검증 정보 수신, 최초 201/재수신 200 |
| POST /api/deposits/parse | X-API-Key | 명시적 수동 형식만 파싱, 확인 필수 |
| GET /api/admin/orders | 관리자 Bearer | limit/offset/status |
| GET /api/admin/deposits | 관리자 Bearer | limit/offset |
| POST /api/admin/deposits | 관리자 Bearer | 수동 미검증 입금 입력 |
| POST /api/admin/orders/{id}/approve | 관리자 Bearer | deposit_id, bank_checked=true, note |
| POST /api/admin/orders/{id}/resend | 관리자 Bearer | note, 종료 작업 새 메일·토큰 발급 |
| POST /api/admin/orders/{id}/reissue | 관리자 Bearer | resend와 동일 (기존 링크 폐기) |
| POST /api/admin/orders/{id}/cancel | 관리자 Bearer | note, 미승인 주문 취소 |
| POST /api/admin/orders/{id}/refund | 관리자 Bearer | note, 실제 환불 후 기록 |
| PATCH /api/admin/settings | 관리자 Bearer | {"price":5000}, 기존 주문 금액 불변 |
| GET /api/admin/email-jobs | 관리자 Bearer | 작업·시도·오류 코드, 암호문 미노출 |
| POST /api/admin/email-jobs/process | 관리자 Bearer | 최대 5개 처리 (worker도 자동 실행) |
| GET /api/admin/mock-mail | 관리자 Bearer | mock 모드에서만 수신함 최근 20개 |
| GET /api/admin/audit | 관리자 Bearer | 승인/취소/환불/재발급/가격 변경 기록 |
| GET /api/admin/export.csv | 관리자 Bearer | 전체 주문, CSV 수식 주입 방지 |
| GET /api/download/{token} | 임의 다운로드 토큰 | 유효기간·폐기·주문 상태 검증 후 파일 |

리스트 기본 limit=100, 최대 500. 입력에 정의되지 않은 필드는 422. 주문의 `amount`나 입금의 `verified`는 입력할 수 없습니다. 입금 시각은 시간대 있는 ISO 8601, 미래 5분 초과는 거부. source 허용값은 manual/shortcut_manual/toss_notification/sms/email/mock이며 모두 미검증입니다.
