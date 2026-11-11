# Cloudflare Tunnel / 고정 HTTPS 도메인

계정·도메인·DNS 변경과 터널 공개는 아직 실행하지 않습니다. 다음은 운영자가 자신의 계정에서 수행하는 절차입니다. 기본 연결은 **구매 페이지와 API를 같은 origin**으로 제공해 CORS를 단순하게 합니다. Pages 데모는 API를 호출하지 않습니다.

## 준비와 계정 설정

1. Cloudflare 계정과 본인 소유 도메인을 준비합니다. 등록 비용과 현재 서비스 요금/약관을 확인합니다. 도메인 등록은 별도 비용이 들 수 있습니다.
2. Cloudflare에 zone을 추가하고 등록기관의 nameserver를 안내된 값으로 변경합니다. 기존 DNS 기록을 보존하고 활성 상태 확인.
3. macOS에서 공식 패키지를 설치합니다: `brew install cloudflared`.
4. 다음 공식 문서를 현재 계정 UI와 함께 확인합니다. [로컬 관리 터널](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/create-local-tunnel/)

```sh
cloudflared tunnel login
cloudflared tunnel create analog-store
```

로그인은 본인이 브라우저에서 도메인을 승인합니다. 출력 UUID와 credentials JSON 경로를 로컬에 기록하세요. `cert.pem`이나 JSON을 저장소·채팅·스크린샷으로 공유하지 않습니다.

## 설정

`deploy/cloudflared.example.yml`을 `~/.cloudflared/config.yml`로 복사하고 UUID·사용자 경로·호스트명을 실제 값으로 교체합니다. 설정과 자격증명 권한을 600으로 제한합니다.

```sh
cloudflared tunnel route dns analog-store store.YOUR-DOMAIN
cloudflared tunnel ingress validate
cloudflared tunnel run analog-store
```

FastAPI는 `127.0.0.1:8000`만 수신합니다. 공유기의 포트 포워딩을 열지 않습니다. 기본 실행기는 proxy header 자동 해석을 끄고, loopback에서 도착한 `CF-Connecting-IP`만 제한 키에 사용합니다. 외부에서 loopback 서비스에 직접 접근할 수 없는 전제가 필요합니다.

`.env`:

```dotenv
PUBLIC_BASE_URL=https://store.YOUR-DOMAIN
ALLOWED_ORIGINS=https://store.YOUR-DOMAIN
LIVE_SALES=false
```

서버 재시작 후 외부 `https://store.YOUR-DOMAIN/health`, 모의 주문, 상태 조회를 확인합니다. `/api/download/<token>` 응답은 캐시하지 않습니다. Cloudflare Cache Rule에서 `/api/*`, `/admin`, `/assets/admin*`를 캐시 우회로 설정하고 요청 URL/본문의 장기 로깅이나 토큰이 포함된 분석 수집은 최소화합니다.

## 관리자와 입금 수신 보호

- Zero Trust → Access → Applications에서 self-hosted 앱 `store.YOUR-DOMAIN/admin` 및 `/api/admin/*`를 추가합니다. 관리자 본인 이메일만 허용하는 정책을 적용하고 비인증 접근이 차단되는지 직접 확인하세요. 경로 매칭 범위를 놓치지 않도록 `/admin*` 보호 여부도 확인합니다.
- Access에 통과한 후에도 서버의 별도 `ADMIN_API_KEY`가 필요합니다. `/assets/admin.html`은 비밀이 없는 빈 껍데기이며 데이터 API는 항상 인증합니다.
- 구매 API 전체에 Access를 걸면 구매자가 로그인해야 하므로 관리자 경로에 한정합니다.
- `/api/deposits`는 별도 `X-API-Key`. Access service token을 추가할 경우 단축어에 `CF-Access-Client-Id`, `CF-Access-Client-Secret` 헤더도 넣습니다. 관리자 앱 정책으로 입금 수신이 막히지 않도록 별도 구성합니다.
- 서버는 IP별 일반 API 180회/분, 주문 생성 10회/시간을 SQLite로 제한합니다. Tunnel 앞단에도 WAF/rate limit을 설정하되 현재 요금제 제공 범위를 확인하세요. CORS는 인증/봇 방어를 대체하지 않습니다. 도메인 전체 대규모 남용에는 edge 차단 또는 Turnstile 같은 별도 검증을 추가할 수 있습니다.

## 재시작과 HTTPS 확인

`cloudflared` 자체의 공식 macOS 서비스 설치 경로는 위 공식 문서의 서비스 실행 안내를 따르세요. 사용자 launchd로 구성한다면 절대경로 `cloudflared`, `tunnel`, `--config`, 실제 설정 경로, `run`, UUID를 ProgramArguments로 전달하고 RunAtLoad/KeepAlive를 설정합니다. server/backup의 launchd 생성기는 `scripts/generate_launchd.py`입니다.

재부팅 후 로그인 여부, FileVault, 네트워크, 절전 설정에 따라 자동 복구가 지연될 수 있습니다. 실제 재부팅 검증 전에는 24시간 무중단을 보장하지 않습니다. 터널 중단 시 기존 주문은 DB에 남고 worker는 실행 중이면 메일 큐를 계속 처리하지만 새 주문/다운로드는 연결 복구까지 사용할 수 없습니다.

## 외부 검증 체크리스트

- [ ] 외부 LTE/5G에서 `/health` 접근
- [ ] 실제 계좌정보 없이 모의 주문 생성 → 새로고침 후 비밀 토큰으로 조회
- [ ] 관리자 경로는 Access + API 키 없이 데이터 조회 불가
- [ ] 아이폰 단축어 POST / 동일 본문 재전송
- [ ] 잘못된 인증 401, 과다 주문 429, 허용되지 않은 Origin의 CORS 차단
- [ ] 로그에 토큰·API 키·구매자 이메일이 기록되지 않는지 점검
- [ ] 터널·서버 재시작 후 DB와 모의 다운로드 권한 유지
